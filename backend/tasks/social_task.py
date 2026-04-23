"""
Celery tasks for social signal collection (Reddit / Twitter / Telegram).

Each task opens its own AsyncSession, pulls active monitors for its platform,
collects posts, scores sentiment + entity matches, generates an embedding,
and inserts with ON CONFLICT DO NOTHING. Twitter and Telegram exit early
with an info log if their env token is missing — graceful skip.
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
                labse_embedding, posted_at
            ) VALUES (
                :platform, :pid, CAST(:mid AS uuid),
                :author, :text, :url,
                :lang,
                :upvotes, :comments, :shares,
                :fwd_count, :fwd_from,
                :has_doc, :doc_url,
                :sentiment, :entities,
                CAST(:emb AS vector), :posted_at
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
        return generate_embedding(text_value)
    except Exception as exc:
        logger.debug("embedding failed: %s", exc)
        return None


async def _process_monitor_posts(
    db,
    monitor_id: str,
    posts: list[dict[str, Any]],
    user_entities: list[str],
) -> int:
    """Insert new posts for a monitor; return count inserted."""
    from backend.collectors.social_collector import (
        compute_sentiment,
        find_matched_entities,
    )

    inserted = 0
    for post in posts:
        pid = post.get("platform_post_id")
        if not pid:
            continue
        if await _post_exists(db, post["platform"], pid):
            continue

        sentiment = compute_sentiment(
            post["post_text"], post.get("post_language", "en")
        )
        matched = find_matched_entities(post["post_text"], user_entities)
        embedding = _safe_embed(post["post_text"])

        try:
            await _insert_post(
                db, monitor_id, post, sentiment, matched, embedding
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

@app.task(name="tasks.collect_reddit", queue="collectors", max_retries=2)
def collect_reddit() -> None:
    """Collect new posts from every active Reddit subreddit monitor."""
    asyncio.run(_collect_reddit())


async def _collect_reddit() -> None:
    from backend.collectors.social_collector import collect_reddit_posts
    from backend.database import get_db

    async with get_db() as db:
        monitors = (
            await db.execute(
                text(
                    "SELECT id, identifier, display_name "
                    "FROM social_monitors "
                    "WHERE platform = 'reddit' AND is_active = TRUE"
                )
            )
        ).fetchall()

        user_entities = await _fetch_user_entities(db)
        total = 0

        for m in monitors:
            posts = await collect_reddit_posts(m.identifier, limit=25)
            total += await _process_monitor_posts(
                db, str(m.id), posts, user_entities
            )
            await _mark_collected(db, str(m.id))

        await db.commit()
        logger.info(
            "Reddit collection done — %s monitors, %s new posts",
            len(monitors),
            total,
        )


# ── Twitter / X ────────────────────────────────────────────────────────────

@app.task(name="tasks.collect_twitter", queue="collectors", max_retries=2)
def collect_twitter() -> None:
    """Collect tweets from every active Twitter account monitor."""
    asyncio.run(_collect_twitter())


async def _collect_twitter() -> None:
    bearer_token = os.getenv("TWITTER_BEARER_TOKEN", "")
    if not bearer_token:
        logger.info(
            "TWITTER_BEARER_TOKEN not set — skipping Twitter collection"
        )
        return

    from backend.collectors.social_collector import (
        collect_twitter_user_tweets,
    )
    from backend.database import get_db

    async with get_db() as db:
        monitors = (
            await db.execute(
                text(
                    "SELECT id, identifier FROM social_monitors "
                    "WHERE platform = 'twitter' AND is_active = TRUE"
                )
            )
        ).fetchall()

        user_entities = await _fetch_user_entities(db)
        total = 0

        for m in monitors:
            posts = await collect_twitter_user_tweets(
                m.identifier, bearer_token, max_results=10
            )
            total += await _process_monitor_posts(
                db, str(m.id), posts, user_entities
            )
            await _mark_collected(db, str(m.id))

        await db.commit()
        logger.info(
            "Twitter collection done — %s monitors, %s new posts",
            len(monitors),
            total,
        )


# ── Telegram ───────────────────────────────────────────────────────────────

@app.task(name="tasks.collect_telegram", queue="collectors", max_retries=2)
def collect_telegram() -> None:
    """Collect recent posts from every active Telegram channel monitor."""
    asyncio.run(_collect_telegram())


async def _collect_telegram() -> None:
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
        monitors = (
            await db.execute(
                text(
                    "SELECT id, identifier FROM social_monitors "
                    "WHERE platform = 'telegram' AND is_active = TRUE"
                )
            )
        ).fetchall()

        user_entities = await _fetch_user_entities(db)
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
                db, str(m.id), posts, user_entities
            )
            await _mark_collected(db, str(m.id))

        await db.commit()
        logger.info(
            "Telegram collection done (%s) — %s monitors, %s new posts",
            "user-account" if use_user_client else "bot-api",
            len(monitors),
            total,
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
