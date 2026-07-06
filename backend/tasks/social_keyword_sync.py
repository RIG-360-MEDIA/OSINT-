"""Keyword-driven social: sync user keyword tracks -> social_watchlist keyword rows.

Part of the store-everything -> keyword-driven switch. Instead of standing broad
targets, social collection is driven by what users actually track: each active
`analytics.keyword_watch` row becomes a `target_type='keyword'` watchlist row on
the platforms whose scrapers support keyword SEARCH (twitter, reddit — see
social_collect._scrape_target). The existing collect_twitter / collect_reddit beat
tasks then sweep those keyword rows on the single social beat. TikTok/WeChat keyword
pulls are served by osint's on-demand social_live path, not here.

Idempotent: upserts on the (platform, target_type, target_value) unique key and
reactivates matches; deactivates only keyword-watch-sourced rows whose track is
gone (never touches corpus/verified/manual rows). Runs on the `social` queue.
"""
from __future__ import annotations

import asyncio
import logging

from backend.celery_app import app

logger = logging.getLogger(__name__)

# Platforms whose scrapers expose a keyword .search() in social_collect._scrape_target.
_KEYWORD_PLATFORMS = ("twitter", "reddit")
_SOURCE = "keyword_watch"


@app.task(name="tasks.social.sync_keyword_watchlist", queue="social")
def sync_keyword_watchlist(client: str = "india_govt") -> dict:
    return asyncio.run(_sync(client))


async def _sync(client: str) -> dict:
    from sqlalchemy import text

    from backend.database import get_db

    async with get_db() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT DISTINCT lower(trim(keyword)) AS kw "
                    "FROM analytics.keyword_watch "
                    "WHERE is_active = TRUE AND coalesce(trim(keyword), '') <> ''"
                )
            )
        ).fetchall()
        keywords = sorted({r.kw for r in rows})

        added = 0
        for kw in keywords:
            for platform in _KEYWORD_PLATFORMS:
                res = await db.execute(
                    text(
                        """
                        INSERT INTO social_watchlist
                            (platform, target_type, target_value, label, source,
                             is_active, client, created_at)
                        VALUES (:p, 'keyword', :kw, :kw, :src, TRUE, :client, NOW())
                        ON CONFLICT (platform, target_type, target_value)
                        DO UPDATE SET is_active = TRUE
                        """
                    ),
                    {"p": platform, "kw": kw, "src": _SOURCE, "client": client},
                )
                added += res.rowcount or 0

        # Retire keyword rows we created whose track no longer exists — scoped to
        # our own source so corpus/verified/manual rows are never touched.
        deact = await db.execute(
            text(
                """
                UPDATE social_watchlist
                SET is_active = FALSE
                WHERE source = :src AND client = :client AND is_active = TRUE
                  AND lower(trim(target_value)) <> ALL(CAST(:kws AS text[]))
                """
            ),
            {"src": _SOURCE, "client": client, "kws": keywords or [""]},
        )
        await db.commit()

    result = {
        "tracked_keywords": len(keywords),
        "rows_upserted": added,
        "rows_deactivated": deact.rowcount or 0,
    }
    if keywords:
        logger.info("sync_keyword_watchlist(%s): %s", client, result)
    return result
