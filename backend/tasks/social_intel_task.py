"""
Signal Room intel layer.

Three Celery tasks, all on the `social` queue:

  - tasks.recompute_social_baselines        (nightly, 02:30 UTC)
        7-day rolling means per entity → social_entity_baselines.

  - tasks.detect_social_events              (every 30 min)
        Six pure-math detection rules → social_events:
          SURGE             — entity volume vs baseline
          SENTIMENT_SHIFT   — entity sentiment delta
          REPETITION        — same source rephrasing same content
          BRIDGE            — story crossed Reddit ↔ Telegram
          SILENCE           — grassroots surge, official silent
          NEW_SUBJECT       — capitalised n-gram not on watchlist

  - tasks.compose_social_summary            (every 6 hours)
        Take last window of events → render typewriter document
        → social_summaries.

No LLM in this module. Every output line traces to a SQL count or delta.
"""
from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from backend.celery_app import app

logger = logging.getLogger(__name__)


# ── Tunables ──────────────────────────────────────────────────────────────

_SURGE_MULTIPLIER: float = 2.0       # 24h ≥ N× baseline AND
_SURGE_MIN_UPLIFT: float = 5.0       # … 24h - baseline ≥ 5 (absolute)
_SURGE_MIN_BASELINE: float = 0.5     # … and baseline ≥ 0.5/day (1+ post in 7d)
_SENTIMENT_SHIFT: float = 0.20       # |Δ| ≥ 0.20 = SENTIMENT_SHIFT
# Tuned 2026-04-29: cluster sizes top out at 3 in the current corpus,
# so ≥3 reposts is statistically unreachable. Drop to 2 — still
# distinguishes "two outlets repeating" from "one-off post".
_REPETITION_MIN: int = 2
_REPETITION_WINDOW_HOURS: int = 36
_BRIDGE_MIN_GAP_MIN: int = 30        # ≥ 30 min gap between platforms
_SILENCE_OFFICIAL_GAP_HOURS: int = 6
_NEW_SUBJECT_MIN_OCC: int = 3
_NEW_SUBJECT_MIN_SOURCES: int = 2

_PROMOTE_MIN_OCC: int = 8            # auto-promote NEW_SUBJECT threshold
_PROMOTE_MIN_SOURCES: int = 3
_PROMOTE_LOOKBACK_HOURS: int = 24
_PROMOTE_MIN_NAME_LEN: int = 4       # reject 1-3 letter "subjects"

# Stop-list of capitalised tokens that pass NEW_SUBJECT detection but are
# clearly not entities — POS noise, sentence-starts, generic categories.
# Anything here is rejected at auto-promote time so it never appears as a
# user-visible "FIGURES ON WATCH" pill on /clips. (clips audit P1-NEW-B)
_PROMOTE_STOPWORDS: frozenset[str] = frozenset(s.lower() for s in {
    # POS noise / sentence-starts
    "Hello", "With", "From", "Open", "Today", "Yesterday", "Tomorrow",
    "Now", "Here", "There", "Then", "When", "Where", "What", "Who",
    "Why", "How", "This", "That", "These", "Those", "Some", "Any",
    "All", "None", "More", "Less", "Most", "Many", "Few", "Such",
    "Also", "Still", "Just", "Even", "Only", "Very", "Quite", "Really",
    # generic categories not worth tracking on their own
    "People", "Police", "Farmers", "Government", "Public", "Citizens",
    "Workers", "Students", "Voters", "Officials", "Authorities",
    "Location", "Date", "Time", "Year", "Month", "Day", "Week",
})


def _is_promotable_subject(name: str) -> bool:
    """Gate before INSERT INTO user_entities for auto-promoted subjects.

    Rejects:
      - blanks / whitespace-only
      - subjects shorter than _PROMOTE_MIN_NAME_LEN
      - case-insensitive matches against _PROMOTE_STOPWORDS

    Note: we deliberately do NOT require presence in entity_dictionary —
    auto-promotion is the mechanism that surfaces *new* entities not yet
    in the dictionary. The stop-list is the safety net.
    """
    if not name:
        return False
    cleaned = name.strip()
    if len(cleaned) < _PROMOTE_MIN_NAME_LEN:
        return False
    if cleaned.lower() in _PROMOTE_STOPWORDS:
        return False
    return True

_BASELINE_DAYS: int = 7
_DEFAULT_WINDOW_HOURS: int = 24
_SUMMARY_WINDOW_HOURS: int = 24


# ────────────────────────────────────────────────────────────────────────
# 1. BASELINES
# ────────────────────────────────────────────────────────────────────────

@app.task(
    name="tasks.recompute_social_baselines",
    queue="social",
    max_retries=1,
)
def recompute_social_baselines() -> None:
    """7-day rolling means per entity. Wipes + rewrites the table."""
    asyncio.run(_recompute_baselines())


async def _recompute_baselines() -> None:
    """Compute 7-day baselines for ALL signal subjects:

      (a) entity match     — `matched_entities[]` ⊇ user_entities
      (b) geo seed         — substring match against geo_seeds.term
      (c) topic seed       — substring match against topic_seeds.term

    Each subject gets one row in `social_entity_baselines`. Same name
    across (a/b/c) collapses via ON CONFLICT — entity matches win on
    correctness because they're computed first.
    """
    from backend.database import get_db

    async with get_db() as db:
        await db.execute(text("DELETE FROM social_entity_baselines"))

        # (a) entity-level baselines from matched_entities[]
        await db.execute(
            text(
                f"""
                INSERT INTO social_entity_baselines
                  (entity, posts_24h, posts_7d_mean, sentiment_24h,
                   sentiment_7d, sources_24h, computed_at)
                SELECT
                    ent AS entity,
                    COUNT(*) FILTER (
                        WHERE collected_at > NOW() - INTERVAL '24 hours'
                    )                                   AS posts_24h,
                    COUNT(*)::float / {_BASELINE_DAYS}  AS posts_7d_mean,
                    AVG(sentiment_score) FILTER (
                        WHERE collected_at > NOW() - INTERVAL '24 hours'
                    )                                   AS sentiment_24h,
                    AVG(sentiment_score)                AS sentiment_7d,
                    COUNT(DISTINCT monitor_id) FILTER (
                        WHERE collected_at > NOW() - INTERVAL '24 hours'
                    )                                   AS sources_24h,
                    NOW()
                FROM (
                    SELECT
                        UNNEST(matched_entities) AS ent,
                        sentiment_score,
                        collected_at,
                        monitor_id
                    FROM social_posts
                    WHERE collected_at > NOW() - INTERVAL '{_BASELINE_DAYS} days'
                      AND matched_entities IS NOT NULL
                      AND cardinality(matched_entities) > 0
                ) flat
                GROUP BY ent
                ON CONFLICT (entity) DO UPDATE SET
                    posts_24h     = EXCLUDED.posts_24h,
                    posts_7d_mean = EXCLUDED.posts_7d_mean,
                    sentiment_24h = EXCLUDED.sentiment_24h,
                    sentiment_7d  = EXCLUDED.sentiment_7d,
                    sources_24h   = EXCLUDED.sources_24h,
                    computed_at   = EXCLUDED.computed_at
                """
            ),
        )

        # (b) + (c) seed-level baselines via substring match against
        # post_text + post_text_translated. Single CROSS JOIN over a
        # UNION of seeds (geo + topic). Skips terms that already have
        # a row from (a) so entity-driven sentiment isn't overwritten.
        await db.execute(
            text(
                f"""
                WITH seeds AS (
                    SELECT term FROM social_geo_seeds
                    UNION
                    SELECT term FROM social_topic_seeds
                    UNION
                    SELECT canonical_name AS term FROM user_entities
                ),
                matches AS (
                    SELECT
                        s.term,
                        sp.collected_at,
                        sp.sentiment_score,
                        sp.monitor_id
                    FROM social_posts sp
                    CROSS JOIN seeds s
                    WHERE sp.collected_at > NOW() - INTERVAL '{_BASELINE_DAYS} days'
                      AND (
                        position(LOWER(s.term) IN LOWER(sp.post_text)) > 0
                        OR position(
                            LOWER(s.term)
                            IN LOWER(COALESCE(sp.post_text_translated, ''))
                        ) > 0
                      )
                )
                INSERT INTO social_entity_baselines
                  (entity, posts_24h, posts_7d_mean, sentiment_24h,
                   sentiment_7d, sources_24h, computed_at)
                SELECT
                    term,
                    COUNT(*) FILTER (
                        WHERE collected_at > NOW() - INTERVAL '24 hours'
                    ),
                    COUNT(*)::float / {_BASELINE_DAYS},
                    AVG(sentiment_score) FILTER (
                        WHERE collected_at > NOW() - INTERVAL '24 hours'
                    ),
                    AVG(sentiment_score),
                    COUNT(DISTINCT monitor_id) FILTER (
                        WHERE collected_at > NOW() - INTERVAL '24 hours'
                    ),
                    NOW()
                FROM matches
                GROUP BY term
                ON CONFLICT (entity) DO UPDATE SET
                    posts_24h     = GREATEST(
                        social_entity_baselines.posts_24h,
                        EXCLUDED.posts_24h
                    ),
                    posts_7d_mean = GREATEST(
                        social_entity_baselines.posts_7d_mean,
                        EXCLUDED.posts_7d_mean
                    ),
                    sentiment_24h = COALESCE(
                        EXCLUDED.sentiment_24h,
                        social_entity_baselines.sentiment_24h
                    ),
                    sentiment_7d  = COALESCE(
                        EXCLUDED.sentiment_7d,
                        social_entity_baselines.sentiment_7d
                    ),
                    sources_24h   = GREATEST(
                        social_entity_baselines.sources_24h,
                        EXCLUDED.sources_24h
                    ),
                    computed_at   = EXCLUDED.computed_at
                """
            ),
        )
        await db.commit()
        logger.info(
            "social baselines recomputed (entities + geo + topic seeds)"
        )


# ────────────────────────────────────────────────────────────────────────
# 1b. AUTO-PROMOTE NEW_SUBJECTS → user_entities
# ────────────────────────────────────────────────────────────────────────


@app.task(
    name="tasks.auto_promote_subjects",
    queue="social",
    max_retries=1,
)
def auto_promote_subjects() -> None:
    """Promote high-volume NEW_SUBJECT events into user_entities daily.

    Threshold: occurrences ≥ _PROMOTE_MIN_OCC AND source_count ≥
    _PROMOTE_MIN_SOURCES. Runs at 02:00 UTC, just before baselines.
    """
    asyncio.run(_auto_promote_subjects())


async def _auto_promote_subjects() -> None:
    from backend.database import get_db

    async with get_db() as db:
        # Anchor promoted subjects to a real user. Pick the user that
        # already owns at least one user_entity (typical 1-user prod
        # case); otherwise abort silently — auto-promote needs an owner.
        owner_row = (
            await db.execute(
                text(
                    """
                    SELECT user_id FROM user_entities
                    GROUP BY user_id
                    ORDER BY COUNT(*) DESC
                    LIMIT 1
                    """
                )
            )
        ).fetchone()
        if not owner_row:
            logger.info(
                "auto-promote skipped — no user_entities owner present"
            )
            return
        owner_id = owner_row.user_id

        rows = (
            await db.execute(
                text(
                    f"""
                    SELECT
                        subject,
                        magnitude,
                        confidence,
                        COALESCE(
                            (metadata->>'source_count')::int, 0
                        ) AS source_count
                    FROM social_events
                    WHERE event_type = 'NEW_SUBJECT'
                      AND detected_at > NOW() - INTERVAL '{_PROMOTE_LOOKBACK_HOURS} hours'
                      AND magnitude >= :min_occ
                      AND COALESCE(
                          (metadata->>'source_count')::int, 0
                      ) >= :min_src
                    ORDER BY magnitude DESC
                    LIMIT 30
                    """
                ),
                {
                    "min_occ": _PROMOTE_MIN_OCC,
                    "min_src": _PROMOTE_MIN_SOURCES,
                },
            )
        ).fetchall()

        promoted = 0
        skipped = 0
        rejected = 0
        for r in rows:
            # P1-NEW-B gate: don't pollute user_entities with POS noise,
            # blanks, or 1-3 letter fragments. Reject before INSERT.
            if not _is_promotable_subject(r.subject):
                rejected += 1
                logger.debug(
                    "auto-promote rejected non-entity '%s'", r.subject,
                )
                continue
            try:
                result = await db.execute(
                    text(
                        """
                        INSERT INTO user_entities
                          (user_id, canonical_name, entity_type,
                           why_watching, priority)
                        VALUES
                          (:uid, :name, 'topic',
                           'auto-promoted from NEW_SUBJECT', 5)
                        ON CONFLICT (user_id, canonical_name) DO NOTHING
                        RETURNING id
                        """
                    ),
                    {"uid": owner_id, "name": r.subject[:200]},
                )
                if result.fetchone():
                    promoted += 1
                else:
                    skipped += 1
            except Exception as exc:
                logger.warning(
                    "auto-promote failed for '%s': %s", r.subject, exc
                )
                skipped += 1

        await db.commit()
        logger.info(
            "auto-promote done — %s promoted, %s skipped (already in), "
            "%s rejected (stop-list/short)",
            promoted, skipped, rejected,
        )


# ────────────────────────────────────────────────────────────────────────
# 2. EVENT DETECTION
# ────────────────────────────────────────────────────────────────────────

@app.task(
    name="tasks.detect_social_events",
    queue="social",
    max_retries=1,
)
def detect_social_events() -> None:
    """Run all six detection rules; persist events."""
    asyncio.run(_detect_events())


async def _detect_events() -> None:
    from backend.database import get_db

    async with get_db() as db:
        # Wipe ALL events first — every detect run produces a fresh
        # snapshot, no duplicates across consecutive runs. Past
        # editions still hold their event_ids array.
        await db.execute(text("DELETE FROM social_events"))

        n_surge = await _detect_surge(db)
        n_shift = await _detect_sentiment_shift(db)
        n_rep = await _detect_repetition(db)
        n_bridge = await _detect_bridge(db)
        n_silence = await _detect_silence(db)
        n_subject = await _detect_new_subjects(db)

        await db.commit()
        logger.info(
            "social events detected — surge=%s shift=%s rep=%s bridge=%s "
            "silence=%s new=%s",
            n_surge, n_shift, n_rep, n_bridge, n_silence, n_subject,
        )


# Rule 1 — SURGE
async def _detect_surge(db) -> int:
    """Fires only when a subject has both:
      • a real history (`posts_7d_mean ≥ _SURGE_MIN_BASELINE`), AND
      • a real spike — both relative (`≥ _SURGE_MULTIPLIER × baseline`)
        and absolute (`24h - baseline ≥ _SURGE_MIN_UPLIFT`).

    The absolute floor kills the cold-start noise where every entity
    looks like "+700%" because the corpus is younger than 7 days and
    the 24h window holds the whole history.
    """
    rows = (
        await db.execute(
            text(
                """
                SELECT
                    b.entity,
                    b.posts_24h,
                    b.posts_7d_mean,
                    b.sources_24h
                FROM social_entity_baselines b
                WHERE b.posts_7d_mean >= :min_baseline
                  AND b.posts_24h::float >= :mult * b.posts_7d_mean
                  AND b.posts_24h::float - b.posts_7d_mean >= :min_uplift
                """
            ),
            {
                "mult": _SURGE_MULTIPLIER,
                "min_uplift": _SURGE_MIN_UPLIFT,
                "min_baseline": _SURGE_MIN_BASELINE,
            },
        )
    ).fetchall()

    n = 0
    for r in rows:
        # Skip stopword-junk that may persist in matched_entities[] /
        # baselines from older auto-promote runs.
        toks = (r.entity or "").lower().split()
        if not toks or all(t in _SUBJECT_STOPWORDS for t in toks):
            continue
        ratio = (
            r.posts_24h / r.posts_7d_mean
            if r.posts_7d_mean
            else float("inf")
        )
        sources = await _entity_sources(db, r.entity)
        conf = (
            "HIGH" if r.sources_24h >= 3
            else "MED" if r.sources_24h >= 2
            else "LOW"
        )
        body = (
            f"{r.entity} mentions at {ratio:.1f}× 7-day baseline "
            f"(24h: {r.posts_24h}, baseline: {r.posts_7d_mean:.1f}/day) "
            f"across {r.sources_24h} source(s)."
        )
        await _insert_event(
            db, "SURGE", r.entity, "entity", ratio, conf, sources, body,
            metadata={
                "posts_24h": r.posts_24h,
                "baseline": r.posts_7d_mean,
            },
        )
        n += 1
    return n


# Rule 2 — SENTIMENT_SHIFT
async def _detect_sentiment_shift(db) -> int:
    rows = (
        await db.execute(
            text(
                """
                SELECT entity, sentiment_24h, sentiment_7d, posts_24h
                FROM social_entity_baselines
                WHERE sentiment_24h IS NOT NULL
                  AND sentiment_7d IS NOT NULL
                  AND ABS(sentiment_24h - sentiment_7d) >= :delta
                  AND posts_24h >= 3
                """
            ),
            {"delta": _SENTIMENT_SHIFT},
        )
    ).fetchall()

    n = 0
    for r in rows:
        toks = (r.entity or "").lower().split()
        if not toks or all(t in _SUBJECT_STOPWORDS for t in toks):
            continue
        delta = r.sentiment_24h - r.sentiment_7d
        direction = "▼" if delta < 0 else "▲"
        sources = await _entity_sources(db, r.entity)
        conf = "HIGH" if abs(delta) >= 0.4 else "MED"
        body = (
            f"{r.entity} sentiment {direction} "
            f"{r.sentiment_7d:+.2f} → {r.sentiment_24h:+.2f} "
            f"(Δ {delta:+.2f}) across {r.posts_24h} post(s)."
        )
        await _insert_event(
            db, "SENTIMENT_SHIFT", r.entity, "entity", abs(delta),
            conf, sources, body,
            metadata={
                "delta": delta,
                "from": r.sentiment_7d,
                "to": r.sentiment_24h,
            },
        )
        n += 1
    return n


# Rule 3 — REPETITION (same source rewording the same content)

# Headline patterns that indicate boilerplate / system messages /
# unavailable content rather than real reposting.
_REPETITION_JUNK_PATTERNS = (
    "couldn't be displayed",
    "could not be displayed",
    "due to copyright",
    "view original",
    "click here",
    "subscribe to view",
    "this message is",
    "channel is unavailable",
    "media not loaded",
    "image not available",
    "loading...",
    "[deleted]",
    "[removed]",
)


async def _detect_repetition(db) -> int:
    """Detect when a single monitor publishes ≥ N near-duplicates inside
    a single cluster within the window. Operates on social_clusters +
    social_cluster_posts already produced by the briefing pipeline.

    Junk filter: skip clusters whose headline matches a system-message
    or boilerplate pattern (those repeat for technical reasons, not
    editorial coordination — we don't want to call them out).
    """
    rows = (
        await db.execute(
            text(
                f"""
                SELECT
                    sc.id          AS cluster_id,
                    sc.headline    AS headline,
                    sm.display_name AS monitor_name,
                    sm.identifier  AS monitor_id,
                    COUNT(*)       AS reposts
                FROM social_clusters sc
                JOIN social_cluster_posts cp ON cp.cluster_id = sc.id
                JOIN social_posts sp ON sp.id = cp.post_id
                LEFT JOIN social_monitors sm ON sm.id = sp.monitor_id
                WHERE sc.window_end > NOW() - INTERVAL '{_REPETITION_WINDOW_HOURS} hours'
                  AND sm.id IS NOT NULL
                GROUP BY sc.id, sc.headline, sm.display_name, sm.identifier
                HAVING COUNT(*) >= :min_reposts
                """
            ),
            {"min_reposts": _REPETITION_MIN},
        )
    ).fetchall()

    n = 0
    for r in rows:
        headline = (r.headline or "").lower()
        if any(pat in headline for pat in _REPETITION_JUNK_PATTERNS):
            continue
        body = (
            f"{r.monitor_name} repeated near-identical phrasing "
            f"{r.reposts}× inside one cluster — "
            f"\"{(r.headline or '')[:60]}…\". "
            f"Pattern suggests rolling talking-points, not new events."
        )
        await _insert_event(
            db, "REPETITION", str(r.cluster_id), "cluster",
            float(r.reposts), "HIGH",
            [r.monitor_id or ""], body,
            metadata={"monitor": r.monitor_name, "reposts": r.reposts},
        )
        n += 1
    return n


# Rule 4 — BRIDGE (story crossed Reddit ↔ Telegram)
async def _detect_bridge(db) -> int:
    rows = (
        await db.execute(
            text(
                f"""
                SELECT
                    sc.id            AS cluster_id,
                    sc.headline      AS headline,
                    sc.platforms     AS platforms,
                    MIN(sp.collected_at) FILTER (
                        WHERE sp.platform = 'reddit'
                    )                AS reddit_first,
                    MIN(sp.collected_at) FILTER (
                        WHERE sp.platform = 'telegram'
                    )                AS telegram_first,
                    COUNT(*)         AS post_count
                FROM social_clusters sc
                JOIN social_cluster_posts cp ON cp.cluster_id = sc.id
                JOIN social_posts sp ON sp.id = cp.post_id
                WHERE sc.platforms @> ARRAY['reddit']::text[]
                  AND sc.platforms @> ARRAY['telegram']::text[]
                  AND sc.window_end > NOW() - INTERVAL '{_DEFAULT_WINDOW_HOURS} hours'
                GROUP BY sc.id, sc.headline, sc.platforms
                """
            )
        )
    ).fetchall()

    n = 0
    for r in rows:
        if not r.reddit_first or not r.telegram_first:
            continue
        gap = abs((r.reddit_first - r.telegram_first).total_seconds()) / 60
        if gap < _BRIDGE_MIN_GAP_MIN:
            continue
        first_platform = (
            "reddit" if r.reddit_first < r.telegram_first else "telegram"
        )
        echo_platform = (
            "telegram" if first_platform == "reddit" else "reddit"
        )
        body = (
            f"Story crossed {first_platform.upper()} → "
            f"{echo_platform.upper()} after "
            f"{gap:.0f} min — \"{(r.headline or '')[:60]}…\". "
            f"{r.post_count} posts spanning both platforms."
        )
        await _insert_event(
            db, "BRIDGE", str(r.cluster_id), "cluster", gap,
            "HIGH", list(r.platforms or []), body,
            metadata={
                "first": first_platform,
                "echo": echo_platform,
                "gap_min": gap,
            },
        )
        n += 1
    return n


# Rule 5 — SILENCE (grassroots talks, official quiet)
async def _detect_silence(db) -> int:
    """An entity surged in non-official sources, but no official
    monitor has posted about it in the last `_SILENCE_OFFICIAL_GAP_HOURS`.
    """
    rows = (
        await db.execute(
            text(
                f"""
                WITH grassroots_volume AS (
                    SELECT UNNEST(sp.matched_entities) AS entity,
                           COUNT(*) AS n
                    FROM social_posts sp
                    LEFT JOIN social_monitors sm ON sm.id = sp.monitor_id
                    WHERE sp.collected_at > NOW() - INTERVAL '24 hours'
                      AND COALESCE(sm.is_official, false) = false
                    GROUP BY entity
                    HAVING COUNT(*) >= 3
                ),
                official_voice AS (
                    SELECT UNNEST(sp.matched_entities) AS entity
                    FROM social_posts sp
                    JOIN social_monitors sm ON sm.id = sp.monitor_id
                    WHERE sm.is_official = true
                      AND sp.collected_at > NOW() - INTERVAL '{_SILENCE_OFFICIAL_GAP_HOURS} hours'
                )
                SELECT g.entity, g.n
                FROM grassroots_volume g
                LEFT JOIN official_voice o
                  ON o.entity = g.entity
                WHERE o.entity IS NULL
                """
            )
        )
    ).fetchall()

    n = 0
    for r in rows:
        # Skip stopword-ish entities that may have leaked into
        # matched_entities[] from older posts pre-stopword-filter.
        toks = (r.entity or "").lower().split()
        if not toks or all(t in _SUBJECT_STOPWORDS for t in toks):
            continue
        body = (
            f"{r.entity} drew {r.n} non-official mentions in 24h; "
            f"no tracked official channel has spoken to it in "
            f"≥{_SILENCE_OFFICIAL_GAP_HOURS}h. INDICATOR. FOLLOW."
        )
        await _insert_event(
            db, "SILENCE", r.entity, "entity", float(r.n),
            "MED", [], body,
            metadata={"grassroots_count": r.n},
        )
        n += 1
    return n


# Rule 6 — NEW_SUBJECT (capitalised n-gram not on watchlist)
_CAP_PATTERN = re.compile(
    r"\b(?:[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){0,3})\b"
)

# Capitalised words that aren't real subjects — sentence starters,
# common pronouns, generic categorisers. Lowercased for comparison.
_SUBJECT_STOPWORDS: frozenset[str] = frozenset({
    "this", "that", "these", "those", "they", "them", "their",
    "there", "here", "what", "which", "where", "when", "why",
    "who", "whom", "whose", "how", "still", "such", "more",
    "most", "many", "much", "some", "any", "every", "all",
    "another", "other", "several", "few", "first", "last",
    "next", "previous", "even", "ever", "never", "nothing",
    "anything", "something", "everything", "nobody", "anyone",
    "someone", "everyone", "after", "before", "during", "between",
    "indian", "indians", "india", "twitter", "facebook", "instagram",
    "youtube", "telegram", "reddit", "whatsapp", "today", "tomorrow",
    "yesterday", "tonight", "morning", "evening", "night",
    "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday", "january", "february", "march", "april",
    "may", "june", "july", "august", "september", "october",
    "november", "december",
    # generic descriptors that look like names but aren't proper nouns
    "chief", "minister", "official", "officials", "officer", "officers",
    "leader", "leaders", "spokesperson", "press", "report", "reports",
    "news", "story", "stories", "update", "updates", "statement",
    "statements", "video", "videos", "photo", "photos", "image",
    "images", "post", "posts", "comment", "comments",
    "english", "hindi", "telugu", "tamil", "kannada",
    # social media noise
    "click", "click here", "subscribe", "follow", "share", "like",
    # sentence connectors / interjections
    "please", "thanks", "thank", "also", "however", "moreover",
    "therefore", "meanwhile", "instead", "rather", "indeed",
    "source", "sources", "via", "regarding", "according",
    "important", "breaking", "exclusive", "watch", "listen",
    "good", "better", "best", "great", "nice", "beautiful",
    "huge", "massive", "big", "small", "true", "false",
    "yes", "no", "maybe", "perhaps", "fine", "okay",
    # imperatives / sentence-starters that look proper-noun-y
    "read", "watch", "look", "looking", "need", "needed", "want",
    "only", "just", "even", "still", "yet", "now", "then",
    "again", "soon", "later", "earlier", "always", "often",
    "sometimes", "rarely", "usually", "actually", "really",
    "quite", "very", "much", "well", "right", "wrong",
    "your", "yours", "ours", "ourselves", "myself", "himself",
    "herself", "itself", "themselves", "you", "yourself",
    # modal verbs / auxiliaries that look proper-noun-y at sentence-start
    "would", "could", "should", "shall", "must", "might", "may",
    "will", "won", "shall", "ought", "dare", "used",
    "wasn", "weren", "isn", "aren", "haven", "hasn", "hadn",
    "didn", "doesn", "don", "can", "cannot", "couldn", "wouldn",
    "shouldn", "mustn", "needn", "going",
    "does", "did", "had", "has", "have", "does", "do",
    # subordinators / connectors at sentence start
    "since", "while", "though", "although", "unless", "until",
    "whether", "because", "when", "where", "wherever", "whenever",
    # job-titles / roles that look proper-noun-y
    "director", "manager", "secretary", "chairman", "chairperson",
    "ceo", "founder", "president", "vice", "deputy", "assistant",
    "professor", "doctor", "engineer", "scientist", "analyst",
    "captain", "lieutenant", "general", "admiral", "colonel",
    "constable", "inspector", "judge", "magistrate", "advocate",
    "speaker", "anchor", "host", "presenter",
    # generic content-tags
    "team", "group", "party", "club", "company", "firm",
    "ministry", "department", "agency", "bureau", "commission",
    "committee", "council", "board", "panel", "forum",
})


async def _detect_new_subjects(db) -> int:
    rows = (
        await db.execute(
            text(
                """
                SELECT
                    sp.id,
                    COALESCE(sp.post_text_translated, sp.post_text) AS body,
                    sm.identifier AS monitor_id
                FROM social_posts sp
                LEFT JOIN social_monitors sm ON sm.id = sp.monitor_id
                WHERE sp.collected_at > NOW() - INTERVAL '24 hours'
                  AND sp.post_text IS NOT NULL
                """
            )
        )
    ).fetchall()
    if not rows:
        return 0

    user_entities = {
        r.canonical_name.lower()
        for r in (
            await db.execute(
                text("SELECT canonical_name FROM user_entities")
            )
        ).fetchall()
        if r.canonical_name
    }

    counts: Counter[str] = Counter()
    sources: dict[str, set[str]] = {}
    for r in rows:
        body = r.body or ""
        for m in _CAP_PATTERN.findall(body):
            term = m.strip()
            term_lc = term.lower()
            if term_lc in user_entities or len(term) < 4:
                continue
            # Filter out single-word entries that are stopwords or
            # generic descriptors. Multi-word phrases pass through —
            # "Hyderabad metro Phase" is interesting; "Hyderabad" alone
            # gets discarded as too generic.
            tokens = term_lc.split()
            if all(t in _SUBJECT_STOPWORDS for t in tokens):
                continue
            counts[term] += 1
            sources.setdefault(term, set()).add(r.monitor_id or "?")

    n = 0
    for term, occ in counts.most_common(30):
        if occ < _NEW_SUBJECT_MIN_OCC:
            continue
        src = sources.get(term, set())
        if len(src) < _NEW_SUBJECT_MIN_SOURCES:
            continue
        body = (
            f'New subject "{term}" — {occ} mentions across '
            f'{len(src)} source(s). Not on watchlist. PROPOSE ADD.'
        )
        await _insert_event(
            db, "NEW_SUBJECT", term, "subject", float(occ),
            "MED" if len(src) >= 3 else "LOW",
            sorted(src), body,
            metadata={"occurrences": occ, "source_count": len(src)},
        )
        n += 1
    return n


# ── Event helpers ──────────────────────────────────────────────────────

async def _entity_sources(db, entity: str) -> list[str]:
    """Sources mentioning `entity` in last 24h.

    Falls back from `matched_entities[]` (entity-driven baselines) to
    substring match on post text + translated text (geo / topic
    seed-driven baselines). The UNION makes SURGE events for
    "Telangana", "water", "election" — which usually have empty
    `matched_entities` — still surface real source codenames.
    """
    rows = (
        await db.execute(
            text(
                """
                SELECT DISTINCT sm.identifier
                FROM social_posts sp
                JOIN social_monitors sm ON sm.id = sp.monitor_id
                WHERE sp.collected_at > NOW() - INTERVAL '24 hours'
                  AND (
                    :entity = ANY(sp.matched_entities)
                    OR position(LOWER(:entity) IN LOWER(sp.post_text)) > 0
                    OR position(
                        LOWER(:entity)
                        IN LOWER(COALESCE(sp.post_text_translated, ''))
                    ) > 0
                  )
                """
            ),
            {"entity": entity},
        )
    ).fetchall()
    return [r.identifier for r in rows if r.identifier]


async def _insert_event(
    db,
    event_type: str,
    subject: str,
    subject_kind: str,
    magnitude: float,
    confidence: str,
    sources: list[str],
    body: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    import json
    await db.execute(
        text(
            """
            INSERT INTO social_events
              (event_type, subject, subject_kind, magnitude,
               confidence, sources, body, metadata)
            VALUES
              (:t, :s, :sk, :m, :c, :src, :b, CAST(:meta AS jsonb))
            """
        ),
        {
            "t": event_type,
            "s": subject[:300],
            "sk": subject_kind,
            "m": float(magnitude or 0),
            "c": confidence,
            "src": sources,
            "b": body,
            "meta": json.dumps(metadata or {}),
        },
    )


# ────────────────────────────────────────────────────────────────────────
# 3. SUMMARY COMPOSER (typewriter document)
# ────────────────────────────────────────────────────────────────────────

@app.task(
    name="tasks.compose_social_summary",
    queue="social",
    max_retries=1,
)
def compose_social_summary() -> None:
    """Compose a 6-hour edition from current events."""
    asyncio.run(_compose_summary())


async def _compose_summary() -> None:
    from backend.database import get_db

    async with get_db() as db:
        events = (
            await db.execute(
                text(
                    f"""
                    SELECT id, event_type, subject, subject_kind,
                           magnitude, confidence, sources, body,
                           metadata, detected_at
                    FROM social_events
                    WHERE detected_at > NOW() - INTERVAL '{_SUMMARY_WINDOW_HOURS} hours'
                    ORDER BY
                        CASE event_type
                            WHEN 'SURGE'           THEN 1
                            WHEN 'SENTIMENT_SHIFT' THEN 2
                            WHEN 'REPETITION'      THEN 3
                            WHEN 'BRIDGE'          THEN 4
                            WHEN 'SILENCE'         THEN 5
                            WHEN 'NEW_SUBJECT'     THEN 6
                            ELSE 7
                        END,
                        magnitude DESC
                    """
                )
            )
        ).fetchall()

        stats = await _gather_glance_stats(db)
        headline = await _gather_headline(db)
        surge_quotes = await _gather_surge_quotes(db, events)
        subject_quotes = await _gather_subject_quotes(db, events)
        sentiment_extremes = await _gather_sentiment_extremes(db)
        official_status = await _gather_official_status(db)

        stationary = (
            await db.execute(
                text(
                    f"""
                    SELECT b.entity
                    FROM social_entity_baselines b
                    WHERE NOT EXISTS (
                        SELECT 1 FROM social_events e
                        WHERE e.subject = b.entity
                          AND e.subject_kind = 'entity'
                          AND e.detected_at > NOW() - INTERVAL '{_SUMMARY_WINDOW_HOURS} hours'
                    )
                    ORDER BY b.posts_24h DESC NULLS LAST
                    LIMIT 14
                    """
                )
            )
        ).fetchall()

        sources_used = (
            await db.execute(
                text(
                    f"""
                    SELECT DISTINCT sm.platform, sm.identifier
                    FROM social_posts sp
                    JOIN social_monitors sm ON sm.id = sp.monitor_id
                    WHERE sp.collected_at > NOW() - INTERVAL '{_SUMMARY_WINDOW_HOURS} hours'
                    """
                )
            )
        ).fetchall()
        sources_list = sorted(
            {
                _codename(s.identifier, s.platform)
                for s in sources_used
                if s.identifier
            }
        )

        next_edition = await _next_edition(db)
        body = _render_summary(
            edition=next_edition,
            events=events,
            stationary=[s.entity for s in stationary],
            sources_used=sources_list,
            stats=stats,
            headline=headline,
            surge_quotes=surge_quotes,
            subject_quotes=subject_quotes,
            sentiment_extremes=sentiment_extremes,
            official_status=official_status,
        )

        await db.execute(
            text(
                """
                INSERT INTO social_summaries
                  (edition, classification, window_hours,
                   body, event_ids, sources_used, metadata)
                VALUES
                  (:ed, 'OPEN', :hours, :body, :ids, :src,
                   CAST(:meta AS jsonb))
                """
            ),
            {
                "ed": next_edition,
                "hours": _SUMMARY_WINDOW_HOURS,
                "body": body,
                "ids": [e.id for e in events],
                "src": sources_list,
                "meta": "{}",
            },
        )
        await db.commit()
        logger.info(
            "summary edition %s composed — %s events, %s sources",
            next_edition, len(events), len(sources_list),
        )


# ── Briefing data gatherers ───────────────────────────────────────────────


async def _gather_glance_stats(db) -> dict[str, Any]:
    row = (
        await db.execute(
            text(
                f"""
                SELECT
                    COUNT(*)                         AS total_posts,
                    COUNT(*) FILTER (
                        WHERE platform = 'reddit'
                    )                                AS reddit_posts,
                    COUNT(*) FILTER (
                        WHERE platform = 'telegram'
                    )                                AS telegram_posts,
                    COUNT(DISTINCT monitor_id)       AS active_sources,
                    COUNT(DISTINCT post_language)    AS distinct_languages,
                    COUNT(*) FILTER (
                        WHERE post_language <> 'en'
                    )                                AS non_english_posts,
                    MIN(collected_at)                AS oldest_post,
                    MAX(collected_at)                AS newest_post
                FROM social_posts
                WHERE collected_at > NOW() - INTERVAL '{_SUMMARY_WINDOW_HOURS} hours'
                """
            )
        )
    ).fetchone()
    if not row or not row.total_posts:
        return {"empty": True}

    # Detect "thin baseline" — corpus age in days
    corpus_age_row = (
        await db.execute(
            text(
                "SELECT NOW() - MIN(collected_at) AS age FROM social_posts"
            )
        )
    ).fetchone()
    corpus_days = (
        corpus_age_row.age.total_seconds() / 86400.0
        if corpus_age_row and corpus_age_row.age else 0.0
    )

    # Top language breakdown
    lang_rows = (
        await db.execute(
            text(
                f"""
                SELECT post_language, COUNT(*) AS n
                FROM social_posts
                WHERE collected_at > NOW() - INTERVAL '{_SUMMARY_WINDOW_HOURS} hours'
                  AND post_language IS NOT NULL
                GROUP BY post_language
                ORDER BY n DESC
                LIMIT 5
                """
            )
        )
    ).fetchall()
    languages = [(r.post_language, int(r.n)) for r in lang_rows]

    return {
        "empty": False,
        "total_posts": int(row.total_posts or 0),
        "reddit_posts": int(row.reddit_posts or 0),
        "telegram_posts": int(row.telegram_posts or 0),
        "active_sources": int(row.active_sources or 0),
        "non_english_posts": int(row.non_english_posts or 0),
        "languages": languages,
        "corpus_days": corpus_days,
        "thin_baseline": corpus_days < 7.0,
    }


async def _gather_headline(db) -> dict[str, Any] | None:
    """Pick the single most-relevant + most-engaged post in the window."""
    row = (
        await db.execute(
            text(
                f"""
                SELECT
                    sp.id::text                AS post_id,
                    sp.platform,
                    COALESCE(sp.post_text_translated, sp.post_text) AS body,
                    sp.post_language,
                    sp.relevance_score,
                    sp.upvotes,
                    sp.comment_count,
                    sm.display_name             AS monitor_name,
                    sm.identifier               AS monitor_id
                FROM social_posts sp
                LEFT JOIN social_monitors sm ON sm.id = sp.monitor_id
                WHERE sp.collected_at > NOW() - INTERVAL '{_SUMMARY_WINDOW_HOURS} hours'
                  AND sp.platform IN ('reddit', 'telegram')
                  AND length(COALESCE(sp.post_text_translated, sp.post_text)) > 20
                ORDER BY
                    sp.relevance_score DESC,
                    (sp.upvotes + 2 * sp.comment_count) DESC,
                    sp.collected_at DESC
                LIMIT 1
                """
            )
        )
    ).fetchone()
    if not row:
        return None
    return {
        "platform": row.platform,
        "monitor": row.monitor_name or row.monitor_id or "?",
        "monitor_codename": _codename(
            row.monitor_id or "?", row.platform,
        ),
        "body": (row.body or "").strip(),
        "relevance": int(row.relevance_score or 0),
        "engagement": int((row.upvotes or 0) + (row.comment_count or 0)),
    }


async def _gather_surge_quotes(
    db, events: list[Any]
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    surge_subjects = [
        e.subject for e in events
        if e.event_type == "SURGE" and e.subject_kind == "entity"
    ]
    for subj in surge_subjects[:10]:
        row = (
            await db.execute(
                text(
                    f"""
                    SELECT
                        COALESCE(sp.post_text_translated, sp.post_text) AS body,
                        sm.identifier AS monitor_id,
                        sm.platform   AS platform
                    FROM social_posts sp
                    LEFT JOIN social_monitors sm ON sm.id = sp.monitor_id
                    WHERE sp.collected_at > NOW() - INTERVAL '{_SUMMARY_WINDOW_HOURS} hours'
                      AND (
                        :subj = ANY(sp.matched_entities)
                        OR position(LOWER(:subj) IN LOWER(sp.post_text)) > 0
                        OR position(
                            LOWER(:subj)
                            IN LOWER(COALESCE(sp.post_text_translated, ''))
                        ) > 0
                      )
                    ORDER BY sp.relevance_score DESC, sp.collected_at DESC
                    LIMIT 1
                    """
                ),
                {"subj": subj},
            )
        ).fetchone()
        if row:
            out[subj] = {
                "body": (row.body or "")[:200].strip(),
                "monitor": _codename(row.monitor_id or "?", row.platform),
            }
    return out


async def _gather_subject_quotes(
    db, events: list[Any]
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    subjects = [
        e.subject for e in events
        if e.event_type == "NEW_SUBJECT"
    ]
    for subj in subjects[:8]:
        row = (
            await db.execute(
                text(
                    f"""
                    SELECT
                        COALESCE(sp.post_text_translated, sp.post_text) AS body,
                        sm.identifier AS monitor_id,
                        sm.platform   AS platform
                    FROM social_posts sp
                    LEFT JOIN social_monitors sm ON sm.id = sp.monitor_id
                    WHERE sp.collected_at > NOW() - INTERVAL '{_SUMMARY_WINDOW_HOURS} hours'
                      AND (
                        position(LOWER(:subj) IN LOWER(sp.post_text)) > 0
                        OR position(
                            LOWER(:subj)
                            IN LOWER(COALESCE(sp.post_text_translated, ''))
                        ) > 0
                      )
                    ORDER BY sp.relevance_score DESC, sp.collected_at DESC
                    LIMIT 1
                    """
                ),
                {"subj": subj},
            )
        ).fetchone()
        if row:
            out[subj] = {
                "body": (row.body or "")[:160].strip(),
                "monitor": _codename(row.monitor_id or "?", row.platform),
            }
    return out


async def _gather_sentiment_extremes(db) -> dict[str, Any]:
    """Pull most-positive and most-negative posts in window."""
    most_pos = (
        await db.execute(
            text(
                f"""
                SELECT
                    COALESCE(sp.post_text_translated, sp.post_text) AS body,
                    sp.sentiment_score,
                    sm.identifier AS monitor_id,
                    sm.platform   AS platform
                FROM social_posts sp
                LEFT JOIN social_monitors sm ON sm.id = sp.monitor_id
                WHERE sp.collected_at > NOW() - INTERVAL '{_SUMMARY_WINDOW_HOURS} hours'
                  AND sp.sentiment_score IS NOT NULL
                  AND length(COALESCE(sp.post_text_translated, sp.post_text)) > 30
                ORDER BY sp.sentiment_score DESC
                LIMIT 1
                """
            )
        )
    ).fetchone()
    most_neg = (
        await db.execute(
            text(
                f"""
                SELECT
                    COALESCE(sp.post_text_translated, sp.post_text) AS body,
                    sp.sentiment_score,
                    sm.identifier AS monitor_id,
                    sm.platform   AS platform
                FROM social_posts sp
                LEFT JOIN social_monitors sm ON sm.id = sp.monitor_id
                WHERE sp.collected_at > NOW() - INTERVAL '{_SUMMARY_WINDOW_HOURS} hours'
                  AND sp.sentiment_score IS NOT NULL
                  AND length(COALESCE(sp.post_text_translated, sp.post_text)) > 30
                ORDER BY sp.sentiment_score ASC
                LIMIT 1
                """
            )
        )
    ).fetchone()
    return {
        "positive": {
            "body": (most_pos.body or "")[:200].strip() if most_pos else "",
            "score": float(most_pos.sentiment_score) if most_pos else 0.0,
            "monitor": (
                _codename(most_pos.monitor_id or "?", most_pos.platform)
                if most_pos else ""
            ),
        } if most_pos else None,
        "negative": {
            "body": (most_neg.body or "")[:200].strip() if most_neg else "",
            "score": float(most_neg.sentiment_score) if most_neg else 0.0,
            "monitor": (
                _codename(most_neg.monitor_id or "?", most_neg.platform)
                if most_neg else ""
            ),
        } if most_neg else None,
    }


async def _gather_official_status(db) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            text(
                """
                SELECT
                    sm.identifier,
                    sm.display_name,
                    sm.platform,
                    sm.last_collected_at,
                    NOW() - sm.last_collected_at AS gap
                FROM social_monitors sm
                WHERE sm.is_active = TRUE
                  AND sm.is_official = TRUE
                ORDER BY sm.last_collected_at DESC NULLS LAST
                LIMIT 12
                """
            )
        )
    ).fetchall()
    out = []
    for r in rows:
        gap_h = (
            r.gap.total_seconds() / 3600.0 if r.gap else 9999.0
        )
        out.append({
            "codename": _codename(r.identifier or "?", r.platform),
            "name": r.display_name or r.identifier,
            "gap_hours": gap_h,
        })
    return out


async def _next_edition(db) -> int:
    row = (
        await db.execute(
            text("SELECT COALESCE(MAX(edition), 0) + 1 AS n FROM social_summaries")
        )
    ).fetchone()
    return int(row.n) if row else 1


def _codename(identifier: str, platform_hint: str = "?") -> str:
    """Compact codename for sources: TG-MIB, R/INDIA, X/HANDLE."""
    ident = (identifier or "?").strip()
    if ident.startswith("r/") or ident.startswith("R/"):
        return ident.upper()
    short = re.sub(r"[^A-Za-z0-9]", "", ident)[:14].upper() or "?"
    if platform_hint == "reddit":
        return f"R/{short}"
    if platform_hint == "twitter":
        return f"X/{short}"
    if platform_hint == "telegram":
        return f"TG-{short}"
    # Unknown platform — fall back to TG- but with a clearer ?
    return f"{short}"


def _dtg() -> str:
    """Date-Time Group, classic military format: 271423Z APR 26."""
    now = datetime.now(timezone.utc)
    return now.strftime("%d%H%MZ %b %y").upper()


def _render_summary(
    *,
    edition: int,
    events: list[Any],
    stationary: list[str],
    sources_used: list[str],
    stats: dict[str, Any] | None = None,
    headline: dict[str, Any] | None = None,
    surge_quotes: dict[str, dict[str, Any]] | None = None,
    subject_quotes: dict[str, dict[str, Any]] | None = None,
    sentiment_extremes: dict[str, Any] | None = None,
    official_status: list[dict[str, Any]] | None = None,
) -> str:
    """Pure-template renderer. Every line traces to numbers in events."""
    today = datetime.now(timezone.utc).strftime("%d %b %Y").upper()
    rule = "═" * 71
    soft = "─" * 71
    stats = stats or {}
    surge_quotes = surge_quotes or {}
    subject_quotes = subject_quotes or {}
    official_status = official_status or []
    out: list[str] = []

    # ── Header ─────────────────────────────────────────────────────
    out.append(
        f"DAILY SIGNAL SUMMARY    {today}    "
        f"EDITION {edition:03d}    OPEN"
    )
    out.append(rule)
    next_edition_at = (
        datetime.now(timezone.utc) + timedelta(hours=6)
    ).strftime("%H%MZ %d %b").upper()
    out.append(
        f"  Window: last {_SUMMARY_WINDOW_HOURS}h     "
        f"Composed: {_dtg()}     Next edition: ≤ {next_edition_at}"
    )
    out.append("")

    # Thin-baseline notice — surfaces when corpus is < 7 days old
    if stats.get("thin_baseline"):
        days = stats.get("corpus_days", 0)
        out.append(
            "  NOTE.  Corpus age is "
            f"{days:.1f} days. 7-day baselines are still warming up; "
            "ratio columns below show the lower-bound estimate. Real"
        )
        out.append(
            "        ratios will appear once a full 7-day window of "
            "data exists."
        )
        out.append("")

    # ── ¶0  AT A GLANCE ────────────────────────────────────────────
    if stats.get("total_posts"):
        out.append(f"¶0  AT A GLANCE                                              {_dtg()}")
        out.append("")
        out.append(
            f"      Posts collected (24h): {stats.get('total_posts', 0)}"
            f"  ·  Reddit {stats.get('reddit_posts', 0)}"
            f"  ·  Telegram {stats.get('telegram_posts', 0)}"
        )
        out.append(
            f"      Active sources: {stats.get('active_sources', 0)}"
            f"   ·  Non-English posts: {stats.get('non_english_posts', 0)}"
            f"   (translated to English for this edition)"
        )
        if stats.get("languages"):
            lang_str = " · ".join(
                f"{lang}:{n}" for lang, n in stats["languages"]
            )
            out.append(f"      Languages: {lang_str}")
        out.append("")

    # ── ¶  HEADLINE — single most-relevant post ────────────────────
    if headline and headline.get("body"):
        out.append(f"¶  HEADLINE  (highest-relevance post in window)              {_dtg()}")
        out.append("")
        body_short = headline["body"][:280]
        if len(headline["body"]) > 280:
            body_short += "…"
        out.append(
            f"      {_wrap(body_short, 67)}"
        )
        out.append(
            f"      — {headline['monitor_codename']}  ·  "
            f"relevance {headline['relevance']}/100  ·  "
            f"engagement {headline['engagement']}"
        )
        out.append("")

    # Group events by type
    by_type: dict[str, list[Any]] = {}
    for e in events:
        by_type.setdefault(e.event_type, []).append(e)

    para = 1

    # ── ¶ SURGES + SHIFTS ──────────────────────────────────────────
    surges = by_type.get("SURGE", [])
    shifts = by_type.get("SENTIMENT_SHIFT", [])
    if surges or shifts:
        out.append(
            f"¶{para}  ENTITIES UNDER SURGE  "
            f"(more chatter than usual, last 24h)"
        )
        out.append("")
        out.append(
            "      Subjects whose mention count in the last 24h is well "
            "above their 7-day average. 'src' = distinct sources."
        )
        out.append("")
        # Sort surges by a credibility score: more sources first (real
        # signal beats single-source noise), then by raw 24h volume.
        surges_sorted = sorted(
            surges,
            key=lambda e: (
                len(e.sources or []),
                int((e.metadata or {}).get("posts_24h", 0)),
            ),
            reverse=True,
        )
        for e in surges_sorted[:20]:
            md = e.metadata or {}
            posts_24h = int(md.get("posts_24h", 0))
            baseline = float(md.get("baseline", 0) or 0)
            sources_n = len(e.sources or [])
            # Smart display — when baseline is artificial (corpus too
            # young) show raw counts instead of a misleading percentage.
            if stats.get("thin_baseline"):
                line = (
                    f"      {e.subject[:30]:<30}  "
                    f"{posts_24h} posts in 24h  ·  "
                    f"{sources_n} src  ·  conf:{e.confidence}"
                )
            else:
                ratio = posts_24h / baseline if baseline > 0 else 0
                line = (
                    f"      {e.subject[:30]:<30}  ↗ {ratio:.1f}× usual  "
                    f"({posts_24h} vs {baseline:.1f}/day, "
                    f"{sources_n} src, conf:{e.confidence})"
                )
            out.append(line)
            # Sample quote (one line)
            q = surge_quotes.get(e.subject)
            if q and q.get("body"):
                quote_short = q["body"][:130].replace("\n", " ")
                if len(q["body"]) > 130:
                    quote_short += "…"
                out.append(
                    f'        ↳ "{quote_short}"  — {q["monitor"]}'
                )
        for e in shifts[:6]:
            md = e.metadata or {}
            arrow = "▼" if md.get("delta", 0) < 0 else "▲"
            tone = "HOSTILE" if md.get("delta", 0) < 0 else "FAVOURABLE"
            out.append(
                f"      {e.subject[:30]:<30}  sentiment turned {tone}  "
                f"{md.get('from', 0):+.2f} → {md.get('to', 0):+.2f}  "
                f"(conf:{e.confidence})"
            )
        out.append("")
        para += 1

    # ── ¶ PHRASING REPETITION ──────────────────────────────────────
    reps = by_type.get("REPETITION", [])
    for e in reps[:5]:
        out.append(
            f"¶{para}  PHRASING REPETITION                                   "
            f"{_dtg()}"
        )
        out.append("")
        out.append(
            "      One source published the same content multiple times, "
            "lightly reworded — typical of a coordinated talking-points"
        )
        out.append("      rollout rather than fresh news events.")
        out.append("")
        out.append(f"      {_wrap(e.body, 67)}")
        out.append(f"      CONF: {e.confidence}.")
        out.append("")
        para += 1

    # ── ¶ BRIDGE ───────────────────────────────────────────────────
    bridges = by_type.get("BRIDGE", [])
    for e in bridges[:5]:
        out.append(
            f"¶{para}  GRASSROOTS ↔ OFFICIAL BRIDGE                          "
            f"{_dtg()}"
        )
        out.append("")
        out.append(
            "      A story crossed between Reddit and Telegram — the same "
            "topic now sits in both grassroots and official streams."
        )
        out.append("")
        out.append(f"      {_wrap(e.body, 67)}")
        out.append(f"      INDICATOR.  FOLLOW for further amplification.")
        out.append("")
        para += 1

    # ── ¶ OFFICIAL SILENCE ─────────────────────────────────────────
    silences = by_type.get("SILENCE", [])
    for e in silences[:5]:
        out.append(
            f"¶{para}  OFFICIAL SILENCE                                      "
            f"{_dtg()}"
        )
        out.append("")
        out.append(
            "      Subject is being discussed by non-official sources, "
            "but no tracked government channel has spoken about it yet."
        )
        out.append("")
        out.append(f"      {_wrap(e.body, 67)}")
        out.append("")
        para += 1

    # ── ¶ SENTIMENT EXTREMES ───────────────────────────────────────
    if sentiment_extremes:
        pos = sentiment_extremes.get("positive")
        neg = sentiment_extremes.get("negative")
        if pos or neg:
            out.append(
                f"¶{para}  SENTIMENT EXTREMES  "
                f"(strongest signal posts in window)"
            )
            out.append("")
            if pos and pos.get("body"):
                out.append(
                    f"      MOST FAVOURABLE  ({pos['score']:+.2f})  "
                    f"— {pos['monitor']}"
                )
                short = pos["body"][:200].replace("\n", " ")
                if len(pos["body"]) > 200:
                    short += "…"
                out.append(f"        \"{_wrap(short, 65)}\"")
                out.append("")
            if neg and neg.get("body"):
                out.append(
                    f"      MOST HOSTILE     ({neg['score']:+.2f})  "
                    f"— {neg['monitor']}"
                )
                short = neg["body"][:200].replace("\n", " ")
                if len(neg["body"]) > 200:
                    short += "…"
                out.append(f"        \"{_wrap(short, 65)}\"")
                out.append("")
            para += 1

    # ── ¶ NEW SUBJECTS ─────────────────────────────────────────────
    new_subj = by_type.get("NEW_SUBJECT", [])
    if new_subj:
        out.append(f"¶{para}  NEW ON THE RADAR  (subjects not on watchlist)")
        out.append("")
        out.append(
            "      Names / phrases the system noticed appearing across "
            "multiple sources but not yet in your tracked entities."
        )
        out.append(
            "      The strongest of these are auto-promoted nightly."
        )
        out.append("")
        for e in new_subj[:8]:
            md = e.metadata or {}
            term = e.subject[:40]
            occ = int(md.get("occurrences", 0))
            srcs = int(md.get("source_count", 0))
            out.append(
                f'      "{term}"  ·  n={occ} / {srcs} src   PROPOSE ADD'
            )
            q = subject_quotes.get(e.subject)
            if q and q.get("body"):
                quote_short = q["body"][:120].replace("\n", " ")
                if len(q["body"]) > 120:
                    quote_short += "…"
                out.append(
                    f'        ↳ "{quote_short}"  — {q["monitor"]}'
                )
        out.append("")
        para += 1

    # ── ¶ OFFICIAL CHANNEL STATUS ──────────────────────────────────
    if official_status:
        out.append(
            f"¶{para}  OFFICIAL CHANNEL STATUS"
            f"  (when each tracked govt source last spoke)"
        )
        out.append("")
        for s in official_status[:10]:
            gap = s.get("gap_hours", 0)
            if gap < 1:
                age = f"{int(gap*60)}m ago"
            elif gap < 24:
                age = f"{gap:.1f}h ago"
            else:
                age = f"{gap/24:.1f}d ago"
            name = (s.get("name") or "?")[:38]
            out.append(
                f"      {s['codename']:<22}  "
                f"{name:<38}  last: {age}"
            )
        out.append("")
        para += 1

    # ── ¶ STATIONARY ───────────────────────────────────────────────
    if stationary:
        out.append(
            f"¶{para}  STATIONARY                                            {_dtg()}"
        )
        out.append("")
        out.append(
            "      Subjects on the watchlist that produced no surge, "
            "shift, or repetition this window."
        )
        out.append("")
        joined = ", ".join(stationary[:14])
        out.append(f"      {_wrap(joined, 67)}")
        out.append("")
        para += 1

    # No-events fallback
    if not events and not stationary:
        out.append(
            f"¶1  NIL                                                       {_dtg()}"
        )
        out.append(
            "      No detected signals in the current window."
        )
        out.append("")

    # ── Source legend + sources used ───────────────────────────────
    out.append(rule)
    out.append("SOURCE LEGEND:")
    out.append("  R/<name>   = Reddit subreddit")
    out.append("  TG-<name>  = Telegram channel  "
               "(prefix TG- so it reads as tradecraft, not branding)")
    out.append("")
    out.append(f"SOURCES (this edition, {len(sources_used)} active):")
    if sources_used:
        src_line = "  " + " · ".join(sources_used)
        out.append(_wrap(src_line, 67))
    else:
        out.append("  (none)")
    out.append(soft)
    out.append(
        "  Pipeline cadence:  Telegram(hot) 15m  ·  Reddit/Telegram(warm) 1h"
    )
    out.append(
        "                     baselines nightly  ·  this summary every 6h"
    )
    out.append(soft)
    out.append("                                                             — END —")
    return "\n".join(out)


def _wrap(text_in: str, width: int) -> str:
    import textwrap
    return "\n      ".join(
        textwrap.wrap(text_in, width=width) or [""]
    )
