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
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        logger.info(
            "TELEGRAM_BOT_TOKEN not set — skipping Telegram collection"
        )
        return

    from backend.collectors.social_collector import collect_telegram_channel
    from backend.database import get_db

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
            posts = await collect_telegram_channel(
                m.identifier, bot_token, limit=20
            )
            total += await _process_monitor_posts(
                db, str(m.id), posts, user_entities
            )
            await _mark_collected(db, str(m.id))

        await db.commit()
        logger.info(
            "Telegram collection done — %s monitors, %s new posts",
            len(monitors),
            total,
        )
