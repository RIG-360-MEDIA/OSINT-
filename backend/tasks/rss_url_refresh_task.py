"""rss_url_refresh_task.py — periodic RSS URL refresher.

When a news site migrates ('site.com/feed' → 'site.com/rss/news'), the
RSS collector silently fails because we keep hitting the old URL. This
task follows 30x redirects and updates `sources.rss_url` to the canonical
final URL.

Runs every 6 hours. Only checks RSS sources with `health_score < 0.5`
(the ones likely to be failing). Free, no LLM.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Optional

import httpx
from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db

logger = logging.getLogger(__name__)

# Rotating browser User-Agents — defeats simple fingerprinting blocks
BROWSER_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
]


def random_ua() -> str:
    return random.choice(BROWSER_UAS)


@app.task(
    name="tasks.refresh_rss_urls",
    autoretry_for=(Exception,),
    max_retries=2,
    default_retry_delay=600,
    soft_time_limit=600,
    time_limit=900,
)
def refresh_rss_urls(limit: int = 80) -> dict:
    """Resolve redirects and update rss_url on any sources hitting MOVED."""
    return asyncio.run(_run(limit))


async def _run(limit: int) -> dict:
    # Pull sources likely to be broken (lower health)
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT id::text AS sid, name, rss_url
              FROM sources
             WHERE source_type = 'rss'
               AND is_active = true
               AND rss_url IS NOT NULL
               AND health_score < 0.5
             ORDER BY health_score ASC, last_collected_at NULLS FIRST
             LIMIT :n
        """), {"n": limit})).mappings().all()

    updated = 0
    confirmed = 0
    failed = 0

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
        for r in rows:
            old_url = r["rss_url"]
            sid = r["sid"]
            try:
                final_url = await _resolve_chain(client, old_url, max_hops=5)
            except Exception as e:  # noqa: BLE001
                logger.debug("refresh: %s -> exception: %s", r["name"], e)
                failed += 1
                continue
            if not final_url or final_url == old_url:
                confirmed += 1
                continue
            # URL changed → persist
            async with get_db() as db:
                await db.execute(text("""
                    UPDATE sources
                       SET rss_url = :u,
                           consecutive_failures = 0,
                           health_score = 0.6
                     WHERE id::text = :sid
                """), {"u": final_url, "sid": sid})
                await db.commit()
            updated += 1
            logger.info("refresh: %s url updated %s -> %s", r["name"], old_url, final_url)

    result = {"checked": len(rows), "url_updated": updated,
              "url_unchanged": confirmed, "fetch_failed": failed}
    logger.info("refresh_rss_urls: %s", result)
    return result


async def _resolve_chain(
    client: httpx.AsyncClient, url: str, max_hops: int = 5
) -> Optional[str]:
    """Manually follow up to `max_hops` redirects with a real UA."""
    current = url
    for _ in range(max_hops):
        try:
            r = await client.get(
                current,
                headers={"User-Agent": random_ua(),
                         "Accept": "application/rss+xml, application/xml, text/xml, */*"},
            )
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.HTTPError):
            return None
        if r.status_code == 200:
            return str(current)
        if r.status_code in (301, 302, 307, 308):
            loc = r.headers.get("location", "")
            if not loc:
                return None
            if loc.startswith("/"):
                # relative redirect — combine with original host
                from urllib.parse import urljoin
                current = urljoin(str(r.request.url), loc)
            else:
                current = loc
            continue
        # any other status — give up
        return None
    return current
