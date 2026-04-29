"""
Briefing pipeline for the Signal Room.

Two Celery tasks:
  - tasks.translate_pending_social_posts — fills `post_text_translated`
    for posts whose `post_language != 'en'`, using the existing
    detect_and_translate utility (Groq for Indian languages,
    deep-translator GoogleTranslate elsewhere).
  - tasks.cluster_recent_social_posts — groups posts in the last
    `_WINDOW_HOURS` window by labse cosine similarity, generates a
    headline + summary per cluster, persists to `social_clusters` /
    `social_cluster_posts`.

Both tasks run on the `social` queue.
"""
from __future__ import annotations

import asyncio
import logging
from collections import Counter
from typing import Any

from sqlalchemy import text

from backend.celery_app import app

logger = logging.getLogger(__name__)


_WINDOW_HOURS: int = 36
_BATCH_TRANSLATE: int = 25
# Tuned 2026-04-29: 0.78 was too tight for cross-platform / cross-
# language posts (Reddit ↔ Telegram, Telugu ↔ English). Result was
# `bridge_candidates: 0` — no cluster ever spanned platforms, so the
# BRIDGE event rule never fired. Drop to 0.72 to admit translated
# near-duplicates while still rejecting unrelated chatter.
_SIMILARITY_THRESHOLD: float = 0.72
_MIN_CLUSTER_SIZE: int = 2
_MAX_CLUSTERS: int = 30
_HEADLINE_MAX: int = 90
_SUMMARY_MAX: int = 240


# ── Translation ────────────────────────────────────────────────────────────


@app.task(
    name="tasks.translate_pending_social_posts",
    queue="social",
    max_retries=1,
)
def translate_pending_social_posts(limit: int = _BATCH_TRANSLATE) -> None:
    """Translate up to `limit` posts whose translation is missing."""
    asyncio.run(_translate_pending(limit))


async def _translate_pending(limit: int) -> None:
    from backend.database import get_db
    from backend.nlp.nlp_language import detect_and_translate

    async with get_db() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT id, post_text, post_language
                    FROM social_posts
                    WHERE post_text_translated IS NULL
                      AND post_language IS NOT NULL
                      AND post_language <> 'en'
                      AND post_text IS NOT NULL
                      AND length(post_text) > 0
                    ORDER BY collected_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            )
        ).fetchall()

        translated = 0
        skipped = 0
        for r in rows:
            try:
                # detect_and_translate accepts (lead, title); we feed
                # the post text twice so it always falls into the
                # working_text branch.
                _lang, en = await detect_and_translate(r.post_text, r.post_text)
                if not en:
                    skipped += 1
                    continue
                await db.execute(
                    text(
                        "UPDATE social_posts "
                        "SET post_text_translated = :en "
                        "WHERE id = :id"
                    ),
                    {"en": en[:3000], "id": r.id},
                )
                translated += 1
            except Exception as exc:
                logger.warning(
                    "translate failed for %s: %s", r.id, exc
                )
                skipped += 1

        await db.commit()
        logger.info(
            "social translation done — %s translated / %s skipped (pool %s)",
            translated,
            skipped,
            len(rows),
        )


# ── Clustering ─────────────────────────────────────────────────────────────


@app.task(
    name="tasks.cluster_recent_social_posts",
    queue="social",
    max_retries=1,
    # P1 fix (2026-04-29): bound total task wall time so a slow LLM
    # response cannot block both slots of the 2-concurrency social
    # worker. soft_time_limit raises SoftTimeLimitExceeded inside the
    # task; time_limit hard-kills it 30s later if the soft signal is
    # ignored.
    soft_time_limit=240,
    time_limit=270,
)
def cluster_recent_social_posts() -> None:
    """Replace the cluster cache for the last _WINDOW_HOURS window."""
    asyncio.run(_cluster_recent())


async def _cluster_recent() -> None:
    from backend.database import get_db

    async with get_db() as db:
        rows = (
            await db.execute(
                text(
                    f"""
                    SELECT
                        sp.id,
                        sp.platform,
                        COALESCE(sp.post_text_translated, sp.post_text) AS body,
                        sp.post_language,
                        sp.sentiment_score,
                        sp.matched_entities,
                        sp.upvotes,
                        sp.comment_count,
                        sp.collected_at,
                        sp.labse_embedding::text AS emb,
                        sm.display_name AS monitor_name
                    FROM social_posts sp
                    LEFT JOIN social_monitors sm ON sm.id = sp.monitor_id
                    WHERE sp.collected_at > NOW() - INTERVAL '{_WINDOW_HOURS} hours'
                      AND sp.labse_embedding IS NOT NULL
                    ORDER BY sp.collected_at DESC
                    LIMIT 800
                    """
                )
            )
        ).fetchall()

        if not rows:
            logger.info("clustering skipped — 0 posts in window")
            return

        posts = [_row_to_post(r) for r in rows]
        clusters = _greedy_cosine_cluster(posts)
        clusters = sorted(
            clusters, key=lambda c: len(c["post_ids"]), reverse=True,
        )[:_MAX_CLUSTERS]

        # Wipe old clusters atomically and rewrite.
        await db.execute(text("DELETE FROM social_clusters"))

        window_start = min(p["collected_at"] for p in posts)
        window_end = max(p["collected_at"] for p in posts)

        for c in clusters:
            members = [p for p in posts if p["id"] in c["post_ids"]]
            headline, summary = _summarise_cluster(members)
            sentiments = [
                p["sentiment"] for p in members if p["sentiment"] is not None
            ]
            avg_sent = sum(sentiments) / len(sentiments) if sentiments else 0.0
            tone = (
                "positive" if avg_sent > 0.15
                else "negative" if avg_sent < -0.15
                else "neutral"
            )
            entity_counter: Counter[str] = Counter()
            for p in members:
                for e in p["entities"]:
                    if e:
                        entity_counter[e] += 1
            top_entities = [e for e, _ in entity_counter.most_common(6)]
            platforms = sorted({p["platform"] for p in members})
            monitor_names = sorted(
                {p["monitor_name"] for p in members if p["monitor_name"]}
            )
            languages = sorted(
                {p["language"] for p in members if p["language"]}
            )
            # Pick top 3 by engagement as the "representative" preview set.
            rep = sorted(
                members,
                key=lambda p: (p["upvotes"] + 2 * p["comments"]),
                reverse=True,
            )[:3]

            inserted = await db.execute(
                text(
                    """
                    INSERT INTO social_clusters (
                        window_start, window_end, headline, summary,
                        post_count, platforms, monitor_names, top_entities,
                        avg_sentiment, sentiment_tone,
                        representative_post_ids, sample_languages
                    ) VALUES (
                        :ws, :we, :head, :sum,
                        :n, :plats, :mons, :ents,
                        :avg, :tone,
                        :reps, :langs
                    )
                    RETURNING id
                    """
                ),
                {
                    "ws": window_start,
                    "we": window_end,
                    "head": headline[:_HEADLINE_MAX],
                    "sum": summary[:_SUMMARY_MAX],
                    "n": len(members),
                    "plats": platforms,
                    "mons": monitor_names[:8],
                    "ents": top_entities,
                    "avg": avg_sent,
                    "tone": tone,
                    "reps": [p["id"] for p in rep],
                    "langs": languages,
                },
            )
            cluster_id = inserted.fetchone().id
            for p in members:
                await db.execute(
                    text(
                        "INSERT INTO social_cluster_posts "
                        "(cluster_id, post_id) VALUES (:c, :p) "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {"c": cluster_id, "p": p["id"]},
                )

        await db.commit()
        logger.info(
            "clustering done — %s clusters from %s posts",
            len(clusters),
            len(posts),
        )


# ── Helpers ────────────────────────────────────────────────────────────────


def _row_to_post(r: Any) -> dict[str, Any]:
    emb_str = r.emb or ""
    try:
        emb = [float(x) for x in emb_str.strip("[]").split(",") if x]
    except Exception:
        emb = []
    return {
        "id": r.id,
        "platform": r.platform,
        "body": r.body or "",
        "language": r.post_language or "en",
        "sentiment": (
            float(r.sentiment_score) if r.sentiment_score is not None else None
        ),
        "entities": list(r.matched_entities or []),
        "upvotes": int(r.upvotes or 0),
        "comments": int(r.comment_count or 0),
        "collected_at": r.collected_at,
        "monitor_name": r.monitor_name,
        "emb": emb,
    }


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _greedy_cosine_cluster(
    posts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Greedy nearest-neighbour clustering on labse embeddings.

    O(n²) but n<=800 here and runs offline. Each unassigned post seeds a
    new cluster, then absorbs every other unassigned post within the
    similarity threshold. Any seed that ends up below `_MIN_CLUSTER_SIZE`
    is dropped (singletons are noise from a "trending stories" lens).
    """
    used: set[Any] = set()
    out: list[dict[str, Any]] = []
    for i, p in enumerate(posts):
        if p["id"] in used or not p["emb"]:
            continue
        members: list[Any] = [p["id"]]
        used.add(p["id"])
        for q in posts[i + 1:]:
            if q["id"] in used or not q["emb"]:
                continue
            if _cosine(p["emb"], q["emb"]) >= _SIMILARITY_THRESHOLD:
                members.append(q["id"])
                used.add(q["id"])
        if len(members) >= _MIN_CLUSTER_SIZE:
            out.append({"post_ids": members})
    return out


def _summarise_cluster(
    members: list[dict[str, Any]],
) -> tuple[str, str]:
    """Produce (headline, summary) for a cluster.

    Strategy: extractive — pick the highest-engagement member's
    translated text. Headline is the first sentence (or first 80 chars);
    summary is the first 240 chars of the same body, plus a tail of
    "(N posts across X channels)" so the user sees aggregation context.
    """
    if not members:
        return ("", "")
    top = max(
        members, key=lambda p: (p["upvotes"] + 2 * p["comments"])
    )
    body = (top["body"] or "").strip().replace("\n", " ")
    if not body:
        body = "(post text unavailable)"
    # Grab the first sentence-ish chunk for the headline.
    head_end = min(
        (i for i in (body.find(". "), body.find("? "), body.find("! "))
         if i > 0),
        default=-1,
    )
    if head_end < 0 or head_end > _HEADLINE_MAX:
        headline = body[:_HEADLINE_MAX].rstrip()
    else:
        headline = body[:head_end].rstrip()
    headline = headline or body[:_HEADLINE_MAX]
    if len(body) > _SUMMARY_MAX - 30:
        tail = body[: _SUMMARY_MAX - 40].rstrip() + "…"
    else:
        tail = body
    monitors = sorted({p["monitor_name"] for p in members if p["monitor_name"]})
    aggr = (
        f"{len(members)} posts"
        + (f" • {', '.join(monitors[:3])}" if monitors else "")
    )
    summary = f"{tail} — {aggr}"[:_SUMMARY_MAX]
    return headline, summary
