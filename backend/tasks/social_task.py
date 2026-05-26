"""
Celery tasks for social signal collection (Reddit / Telegram).

Each task opens its own AsyncSession, pulls active monitors for its platform,
collects posts, scores sentiment + entity matches, generates an embedding,
and inserts with ON CONFLICT DO NOTHING. Telegram exits early with an info
log if its credentials are missing — graceful skip.

Twitter was removed on 2026-04-29 — the X API free tier returns HTTP 402
on user lookups. Restore from git tag pre-twitter-removal if a paid tier
is procured.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any

from sqlalchemy import text

from backend.celery_app import app

logger = logging.getLogger(__name__)


# ── Shared helpers ─────────────────────────────────────────────────────────

async def _fetch_entity_pool(db) -> tuple[list[str], dict[str, list[str]]]:
    """Pull the full entity_dictionary as `(canonical_names, aliases_map)`.

    Used at ingestion time to tag posts globally — per CLAUDE.md the
    project follows "global ingestion, per-user view filtering by
    entity". 11k+ rows; cheap to load once per task.
    """
    try:
        result = await db.execute(
            text(
                "SELECT canonical_name, aliases "
                "FROM entity_dictionary"
            )
        )
        names: list[str] = []
        aliases: dict[str, list[str]] = {}
        for r in result.fetchall():
            cn = r.canonical_name
            if not cn:
                continue
            names.append(cn)
            aliases[cn] = list(r.aliases or [])
        return names, aliases
    except Exception as exc:
        logger.warning("entity_pool fetch failed: %s", exc)
        return [], {}


async def _fetch_user_entities(db) -> list[str]:
    """Pull canonical entity names across all users for post-tagging."""
    try:
        result = await db.execute(
            text("SELECT DISTINCT canonical_name FROM user_entities")
        )
        return [r.canonical_name for r in result.fetchall() if r.canonical_name]
    except Exception as exc:
        logger.warning("user_entities fetch failed: %s", exc)
        return []


async def _fetch_geo_seeds(db) -> list[str]:
    try:
        rows = (
            await db.execute(
                text("SELECT term FROM social_geo_seeds")
            )
        ).fetchall()
        return [r.term for r in rows if r.term]
    except Exception as exc:
        logger.warning("geo_seeds fetch failed: %s", exc)
        return []


async def _fetch_topic_seeds(db) -> list[str]:
    try:
        rows = (
            await db.execute(
                text("SELECT term FROM social_topic_seeds")
            )
        ).fetchall()
        return [r.term for r in rows if r.term]
    except Exception as exc:
        logger.warning("topic_seeds fetch failed: %s", exc)
        return []


def _compute_relevance(
    post_text: str,
    matched_entities: list[str],
    sentiment: float,
    is_official_monitor: bool,
    geo_seeds: list[str],
    topic_seeds: list[str],
) -> int:
    """Compute per-post relevance score 0-100.

    Static signals only (no cluster / engagement / freshness — those are
    computed at read time or recomputed by a periodic task):
      +25 entity match
      +20 official monitor source
      +15 geo seed mention
      +15 topic seed mention
      +5  sentiment extremity (|score| >= 0.5)
    Capped at 100.
    """
    if not post_text:
        return 0
    haystack = post_text.lower()
    score = 0
    if matched_entities:
        score += 25
    if is_official_monitor:
        score += 20
    if any(g.lower() in haystack for g in geo_seeds if g):
        score += 15
    if any(t.lower() in haystack for t in topic_seeds if t):
        score += 15
    if sentiment is not None and abs(sentiment) >= 0.5:
        score += 5
    return min(score, 100)


async def _post_exists(db, platform: str, platform_post_id: str) -> bool:
    result = await db.execute(
        text(
            "SELECT 1 FROM social_posts "
            "WHERE platform = :p AND platform_post_id = :pid LIMIT 1"
        ),
        {"p": platform, "pid": platform_post_id},
    )
    return result.fetchone() is not None


def _parse_iso(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp (or pass datetime through) — asyncpg is
    strict about timestamptz binds and rejects plain strings."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def _insert_post(
    db,
    monitor_id: str,
    post: dict[str, Any],
    sentiment: float,
    matched: list[str],
    embedding: list[float] | None,
    relevance_score: int = 0,
) -> None:
    emb_str = str(embedding) if embedding else None
    posted_at = _parse_iso(post.get("posted_at"))
    await db.execute(
        text(
            """
            INSERT INTO social_posts (
                platform, platform_post_id, monitor_id,
                author_username, post_text, post_url,
                post_language,
                upvotes, comment_count, share_count,
                forward_count, forwarded_from,
                has_document, document_url,
                sentiment_score, matched_entities,
                labse_embedding, posted_at, relevance_score
            ) VALUES (
                :platform, :pid, CAST(:mid AS uuid),
                :author, :text, :url,
                :lang,
                :upvotes, :comments, :shares,
                :fwd_count, :fwd_from,
                :has_doc, :doc_url,
                :sentiment, :entities,
                CAST(:emb AS vector), :posted_at, :rel
            )
            ON CONFLICT (platform, platform_post_id) DO NOTHING
            """
        ),
        {
            "platform": post["platform"],
            "pid": post["platform_post_id"],
            "mid": monitor_id,
            "author": post.get("author_username") or "",
            "text": post["post_text"],
            "url": post.get("post_url") or "",
            "lang": post.get("post_language") or "en",
            "upvotes": int(post.get("upvotes") or 0),
            "comments": int(post.get("comment_count") or 0),
            "shares": int(post.get("share_count") or 0),
            "fwd_count": int(post.get("forward_count") or 0),
            "fwd_from": post.get("forwarded_from") or "",
            "has_doc": bool(post.get("has_document")),
            "doc_url": post.get("document_url"),
            "sentiment": float(sentiment),
            "entities": matched,
            "emb": emb_str,
            "posted_at": posted_at,
            "rel": int(relevance_score),
        },
    )


async def _mark_collected(db, monitor_id: str) -> None:
    await db.execute(
        text(
            "UPDATE social_monitors SET last_collected_at = NOW() "
            "WHERE id = CAST(:mid AS uuid)"
        ),
        {"mid": monitor_id},
    )


def _safe_embed(text_value: str) -> list[float] | None:
    try:
        from backend.nlp.nlp_embedding import generate_embedding
        from backend.nlp.embed_guard import safe_embed_input  # T15
        _safe = safe_embed_input(text_value)
        if _safe is None:
            return None
        return generate_embedding(_safe)
    except Exception as exc:
        logger.debug("embedding failed: %s", exc)
        return None


def _detect_language(text_value: str, fallback: str = "en") -> str:
    """SIG-13: detect post language so VADER isn't run on non-English text.

    Tries `langdetect`; on any failure (library missing, ambiguous text,
    very short input) falls back to the provider-supplied or default
    language. Always returns a 2-letter ISO code.
    """
    if not text_value or len(text_value.strip()) < 8:
        return fallback
    try:
        from langdetect import DetectorFactory, detect

        DetectorFactory.seed = 0  # deterministic
        return detect(text_value) or fallback
    except Exception as exc:
        logger.debug("language detect failed: %s", exc)
        return fallback


async def _process_monitor_posts(
    db,
    monitor_id: str,
    posts: list[dict[str, Any]],
    user_entities: list[str],
    is_official_monitor: bool = False,
    geo_seeds: list[str] | None = None,
    topic_seeds: list[str] | None = None,
    entity_aliases: dict[str, list[str]] | None = None,
) -> int:
    """Insert new posts for a monitor; return count inserted.

    Computes static relevance_score per post at insert time. Dynamic
    signals (cluster membership, engagement-percentile, freshness) are
    computed at read time in API queries.

    `user_entities` here is the *ingestion pool* (typically the full
    entity_dictionary canonical_names — see `_fetch_entity_pool`). View
    filtering by user happens at query time in `signals_router`.
    """
    from backend.collectors.social_collector import (
        compute_sentiment,
        find_matched_entities,
    )

    geo_seeds = geo_seeds or []
    topic_seeds = topic_seeds or []
    entity_aliases = entity_aliases or {}
    inserted = 0
    for post in posts:
        pid = post.get("platform_post_id")
        if not pid:
            continue
        if await _post_exists(db, post["platform"], pid):
            continue

        # SIG-13: respect provider lang when present, otherwise detect.
        provider_lang = post.get("post_language")
        if not provider_lang or provider_lang == "en":
            detected = _detect_language(post["post_text"], fallback="en")
            post["post_language"] = detected
        sentiment = compute_sentiment(
            post["post_text"], post.get("post_language", "en")
        )
        matched = find_matched_entities(
            post["post_text"],
            user_entities,
            text_translated=post.get("post_text_translated"),
            aliases=entity_aliases,
        )
        embedding = _safe_embed(post["post_text"])
        relevance = _compute_relevance(
            post_text=post["post_text"],
            matched_entities=matched,
            sentiment=sentiment,
            is_official_monitor=is_official_monitor,
            geo_seeds=geo_seeds,
            topic_seeds=topic_seeds,
        )

        try:
            await _insert_post(
                db, monitor_id, post, sentiment, matched, embedding,
                relevance_score=relevance,
            )
            inserted += 1
        except Exception as exc:
            logger.warning(
                "%s insert failed (%s): %s",
                post["platform"],
                pid,
                exc,
            )
    return inserted


# ── Reddit ─────────────────────────────────────────────────────────────────

@app.task(name="tasks.collect_reddit", queue="social", max_retries=2)
def collect_reddit(tier: str | None = None) -> None:
    """Collect from active Reddit monitors. `tier` filter optional."""
    asyncio.run(_collect_reddit(tier))


async def _collect_reddit(tier: str | None = None) -> None:
    from backend.collectors.social_collector import collect_reddit_posts
    from backend.database import get_db

    async with get_db() as db:
        clause = "AND tier = :tier" if tier else ""
        monitors = (
            await db.execute(
                text(
                    "SELECT id, identifier, display_name, "
                    "       is_official, tier "
                    "FROM social_monitors "
                    f"WHERE platform = 'reddit' AND is_active = TRUE {clause}"
                ),
                {"tier": tier} if tier else {},
            )
        ).fetchall()

        user_entities, entity_aliases = await _fetch_entity_pool(db)
        if not user_entities:
            # Fall back to user_entities if dictionary is empty/unavailable
            user_entities = await _fetch_user_entities(db)
            entity_aliases = {}
        geo_seeds = await _fetch_geo_seeds(db)
        topic_seeds = await _fetch_topic_seeds(db)
        total = 0

        for m in monitors:
            posts = await collect_reddit_posts(m.identifier, limit=25)
            total += await _process_monitor_posts(
                db, str(m.id), posts, user_entities,
                is_official_monitor=bool(m.is_official),
                geo_seeds=geo_seeds,
                topic_seeds=topic_seeds,
                entity_aliases=entity_aliases,
            )
            await _mark_collected(db, str(m.id))

        await db.commit()
        logger.info(
            "Reddit collection done — tier=%s, %s monitors, %s new posts",
            tier or "all", len(monitors), total,
        )


# ── Twitter / X ────────────────────────────────────────────────────────────
# Removed 2026-04-29. Twitter API free tier (HTTP 402) makes collection
# non-functional. Code preserved in git history (tag pre-twitter-removal).
# Restore tasks.collect_twitter and the matching collector functions if a
# paid X tier is procured.


# ── Telegram ───────────────────────────────────────────────────────────────

@app.task(name="tasks.collect_telegram", queue="social", max_retries=2)
def collect_telegram(tier: str | None = None) -> None:
    """Collect from active Telegram monitors. `tier` filter optional."""
    asyncio.run(_collect_telegram(tier))


async def _collect_telegram(tier: str | None = None) -> None:
    """
    Prefer user-account (MTProto/Telethon) collection when
    TELEGRAM_API_ID/HASH/SESSION_STRING are set — this reads any public
    channel without membership. Fall back to Bot API polling when only
    TELEGRAM_BOT_TOKEN is set (requires the bot to be a channel member).
    """
    api_id_raw = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    session_string = os.getenv("TELEGRAM_SESSION_STRING", "").strip()
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

    use_user_client = bool(api_id_raw and api_hash and session_string)
    use_bot = bool(bot_token) and not use_user_client

    if not (use_user_client or use_bot):
        logger.info(
            "Telegram: no credentials configured — skipping "
            "(set TELEGRAM_API_ID + TELEGRAM_API_HASH + "
            "TELEGRAM_SESSION_STRING for user-account mode, or "
            "TELEGRAM_BOT_TOKEN for bot mode)"
        )
        return

    api_id: int = 0
    if use_user_client:
        try:
            api_id = int(api_id_raw)
        except ValueError:
            logger.warning(
                "TELEGRAM_API_ID is not an integer — aborting"
            )
            return

    from backend.database import get_db

    if use_user_client:
        from backend.collectors.telegram_user_collector import (
            collect_telegram_channel_as_user,
        )
    else:
        from backend.collectors.social_collector import (
            collect_telegram_channel,
        )

    async with get_db() as db:
        clause = "AND tier = :tier" if tier else ""
        monitors = (
            await db.execute(
                text(
                    "SELECT id, identifier, is_official, tier "
                    "FROM social_monitors "
                    f"WHERE platform = 'telegram' AND is_active = TRUE {clause}"
                ),
                {"tier": tier} if tier else {},
            )
        ).fetchall()

        user_entities, entity_aliases = await _fetch_entity_pool(db)
        if not user_entities:
            # Fall back to user_entities if dictionary is empty/unavailable
            user_entities = await _fetch_user_entities(db)
            entity_aliases = {}
        geo_seeds = await _fetch_geo_seeds(db)
        topic_seeds = await _fetch_topic_seeds(db)
        total = 0

        for m in monitors:
            if use_user_client:
                posts = await collect_telegram_channel_as_user(
                    m.identifier,
                    api_id,
                    api_hash,
                    session_string,
                    limit=20,
                )
            else:
                posts = await collect_telegram_channel(
                    m.identifier, bot_token, limit=20
                )
            total += await _process_monitor_posts(
                db, str(m.id), posts, user_entities,
                is_official_monitor=bool(m.is_official),
                geo_seeds=geo_seeds,
                topic_seeds=topic_seeds,
                entity_aliases=entity_aliases,
            )
            await _mark_collected(db, str(m.id))

        await db.commit()
        logger.info(
            "Telegram collection done (%s) — tier=%s, %s monitors, %s new posts",
            "user-account" if use_user_client else "bot-api",
            tier or "all", len(monitors), total,
        )


# ── Daily sentiment aggregation ────────────────────────────────────────────

# Sentiment thresholds (compute_sentiment returns roughly -1..+1)
_POS_THRESHOLD: float = 0.15
_NEG_THRESHOLD: float = -0.15
_TOP_ENTITY_LIMIT: int = 10
_AGGREGATION_LOOKBACK_DAYS: int = 7


@app.task(
    name="tasks.aggregate_social_sentiment_daily",
    queue="nlp",
    max_retries=2,
)
def aggregate_social_sentiment_daily() -> None:
    """Roll up social_posts into per-monitor per-day sentiment buckets.

    Idempotent via UNIQUE(monitor_id, date) + ON CONFLICT DO UPDATE so it
    can re-run safely. Looks back N days to catch late-arriving posts.
    """
    asyncio.run(_aggregate_social_sentiment_daily())


async def _aggregate_social_sentiment_daily() -> None:
    from backend.database import get_db

    async with get_db() as db:
        # One pass: aggregate by (monitor_id, platform, date) over the
        # lookback window. UNNEST flattens matched_entities so we can
        # rank top entities per bucket.
        result = await db.execute(
            text(
                """
                WITH bucketed AS (
                    SELECT
                        sp.monitor_id,
                        sp.platform,
                        DATE(sp.posted_at) AS bucket_date,
                        sp.sentiment_score,
                        sp.matched_entities
                    FROM social_posts sp
                    WHERE sp.monitor_id IS NOT NULL
                      AND sp.posted_at IS NOT NULL
                      AND sp.posted_at >= NOW() - (
                          :lookback || ' days'
                      )::interval
                ),
                entity_counts AS (
                    SELECT
                        monitor_id,
                        bucket_date,
                        entity,
                        COUNT(*) AS ec
                    FROM bucketed,
                         LATERAL UNNEST(matched_entities) AS entity
                    WHERE entity IS NOT NULL AND entity <> ''
                    GROUP BY monitor_id, bucket_date, entity
                ),
                top_entities AS (
                    SELECT
                        monitor_id,
                        bucket_date,
                        ARRAY_AGG(
                            entity ORDER BY ec DESC
                        ) FILTER (WHERE rn <= :top_n) AS top
                    FROM (
                        SELECT
                            monitor_id,
                            bucket_date,
                            entity,
                            ec,
                            ROW_NUMBER() OVER (
                                PARTITION BY monitor_id, bucket_date
                                ORDER BY ec DESC
                            ) AS rn
                        FROM entity_counts
                    ) ranked
                    GROUP BY monitor_id, bucket_date
                )
                SELECT
                    b.monitor_id,
                    b.platform,
                    b.bucket_date,
                    COUNT(*) AS post_count,
                    COUNT(*) FILTER (
                        WHERE b.sentiment_score >= :pos
                    ) AS positive_count,
                    COUNT(*) FILTER (
                        WHERE b.sentiment_score <= :neg
                    ) AS negative_count,
                    COUNT(*) FILTER (
                        WHERE b.sentiment_score > :neg
                          AND b.sentiment_score < :pos
                    ) AS neutral_count,
                    AVG(b.sentiment_score) AS avg_sentiment,
                    COALESCE(te.top, ARRAY[]::TEXT[]) AS top_entities
                FROM bucketed b
                LEFT JOIN top_entities te
                  ON te.monitor_id = b.monitor_id
                 AND te.bucket_date = b.bucket_date
                GROUP BY
                    b.monitor_id, b.platform, b.bucket_date, te.top
                """
            ),
            {
                "lookback": str(_AGGREGATION_LOOKBACK_DAYS),
                "pos": _POS_THRESHOLD,
                "neg": _NEG_THRESHOLD,
                "top_n": _TOP_ENTITY_LIMIT,
            },
        )

        rows = result.fetchall()
        upserts = 0

        for r in rows:
            await db.execute(
                text(
                    """
                    INSERT INTO social_sentiment_daily (
                        monitor_id, date, platform,
                        positive_count, negative_count, neutral_count,
                        avg_sentiment, post_count, top_entities
                    ) VALUES (
                        :mid, :d, :platform,
                        :pos, :neg, :neu,
                        :avg, :count, :entities
                    )
                    ON CONFLICT (monitor_id, date) DO UPDATE SET
                        platform = EXCLUDED.platform,
                        positive_count = EXCLUDED.positive_count,
                        negative_count = EXCLUDED.negative_count,
                        neutral_count = EXCLUDED.neutral_count,
                        avg_sentiment = EXCLUDED.avg_sentiment,
                        post_count = EXCLUDED.post_count,
                        top_entities = EXCLUDED.top_entities
                    """
                ),
                {
                    "mid": str(r.monitor_id),
                    "d": r.bucket_date,
                    "platform": r.platform,
                    "pos": int(r.positive_count or 0),
                    "neg": int(r.negative_count or 0),
                    "neu": int(r.neutral_count or 0),
                    "avg": float(r.avg_sentiment or 0.0),
                    "count": int(r.post_count or 0),
                    "entities": list(r.top_entities or []),
                },
            )
            upserts += 1

        await db.commit()
        logger.info(
            "social_sentiment_daily aggregation done — %s buckets upserted",
            upserts,
        )


# ── Entity backfill (SIG-10) ───────────────────────────────────────────────


@app.task(
    name="tasks.backfill_social_entity_matches",
    queue="social",
    max_retries=1,
)
def backfill_social_entity_matches() -> None:
    """Re-tag existing social_posts with the current user_entities pool.

    Entity matching at original collection time is best-effort: posts
    inserted before a user added their first entity will have empty
    matched_entities. This task scans all posts and rewrites the array
    where it differs from a fresh substring match. Idempotent.
    """
    asyncio.run(_backfill_social_entity_matches())


async def _backfill_social_entity_matches() -> None:
    from backend.collectors.social_collector import find_matched_entities
    from backend.database import get_db

    async with get_db() as db:
        user_entities, entity_aliases = await _fetch_entity_pool(db)
        if not user_entities:
            user_entities = await _fetch_user_entities(db)
            entity_aliases = {}
        if not user_entities:
            logger.info("entity backfill skipped — no entities available")
            return

        rows = (
            await db.execute(
                text(
                    "SELECT id, post_text, post_text_translated, "
                    "matched_entities "
                    "FROM social_posts"
                )
            )
        ).fetchall()

        updated = 0
        for r in rows:
            current = list(r.matched_entities or [])
            fresh = find_matched_entities(
                r.post_text or "",
                user_entities,
                text_translated=r.post_text_translated,
                aliases=entity_aliases,
            )
            if sorted(current) == sorted(fresh):
                continue
            await db.execute(
                text(
                    "UPDATE social_posts SET matched_entities = :ents "
                    "WHERE id = :id"
                ),
                {"ents": fresh, "id": r.id},
            )
            updated += 1

        await db.commit()
        logger.info(
            "entity backfill done — %s/%s posts re-tagged against %s entities (with %s aliases)",
            updated,
            len(rows),
            len(user_entities),
            sum(len(v) for v in entity_aliases.values()),
        )
