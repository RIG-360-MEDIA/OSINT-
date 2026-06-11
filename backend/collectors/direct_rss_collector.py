"""
Direct RSS Collector — fetches RSS feeds that FreshRSS refuses to subscribe.

FreshRSS rejects ~125 of our DB sources with HTTP 400 (its internal validator
fails on bot-blocked feeds, expired Feedburner redirects, or feeds returning
HTML instead of XML). This collector picks up the orphans:

  - Source rows where source_type='rss', is_active=true, rss_url is set,
    BUT no matching FreshRSS subscription exists.

It fetches each rss_url directly with browser-grade headers, parses with
feedparser, and inserts articles using the same pipeline as RSSCollector
(URL hashing, dedup, TieredFetcher for body extraction).

Auto-disables sources that fail 10 times in a row, mirroring RSSCollector.

Run manually:
    docker exec rig-backend python -m backend.collectors.direct_rss_collector
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import asyncpg
import feedparser
import httpx

from backend.collectors.tiered_fetcher import TieredFetcher

logger = logging.getLogger(__name__)

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL_SYNC", "postgresql://rig:rigpassword@rig-postgres:5432/rig"
)
FRESHRSS_URL: str = os.environ.get("FRESHRSS_URL", "http://rig-freshrss:80").rstrip("/")
FRESHRSS_USERNAME: str = os.environ.get("FRESHRSS_USERNAME", "admin")
FRESHRSS_PASSWORD: str = os.environ.get("FRESHRSS_PASSWORD", "")

LEAD_TEXT_MAX_CHARS = 2000
MIN_FULL_TEXT_CHARS = 50
ITEMS_PER_FEED = 20
FEED_FETCH_TIMEOUT = 20
MAX_CONCURRENT_FEEDS = 8

# Browser-grade headers — many publishers 403 generic Python clients but accept
# requests that look like a real browser. We rotate the User-Agent across 6
# different desktop/mobile profiles to defeat simple fingerprinting blocks
# (sites that ban one specific UA but allow others).
_BROWSER_UAS: tuple[str, ...] = (
    # Chrome 124 / Windows 10
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome 124 / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Safari 17.4 / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    # Firefox 124 / Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    # Firefox 124 / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    # Safari 17.4 / iPhone
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
)


def _browser_headers() -> dict[str, str]:
    """Returns a fresh headers dict with a randomly-chosen User-Agent.

    Rotating per-request defeats sites that block one specific UA string.
    """
    import random as _random  # local import keeps module-level scope clean
    return {
        "User-Agent": _random.choice(_BROWSER_UAS),
        "Accept": (
            "application/rss+xml, application/atom+xml, application/xml;q=0.9, "
            "text/xml;q=0.8, */*;q=0.5"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


# Backward-compat — some callers reference the old constant name. Returns
# the first UA in the rotation so existing code keeps working without imports.
_BROWSER_HEADERS: dict[str, str] = _browser_headers()


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode()).hexdigest()


def _host_from_url(url: str) -> str:
    return urlparse(url.lower()).netloc.lstrip("www.")


# ---------------------------------------------------------------------------
# FreshRSS subscription lookup (so we only fetch orphans)
# ---------------------------------------------------------------------------


async def _freshrss_subscription_urls(client: httpx.AsyncClient) -> set[str]:
    """Returns the set of feed URLs already subscribed in FreshRSS."""
    try:
        auth_resp = await client.post(
            f"{FRESHRSS_URL}/api/greader.php/accounts/ClientLogin",
            data={"Email": FRESHRSS_USERNAME, "Passwd": FRESHRSS_PASSWORD},
            timeout=15,
        )
        auth_resp.raise_for_status()
        token: str | None = None
        for line in auth_resp.text.splitlines():
            if line.startswith("Auth="):
                token = line[5:].strip()
                break
        if not token:
            logger.warning("FreshRSS auth: no token in response — assuming empty set")
            return set()
        list_resp = await client.get(
            f"{FRESHRSS_URL}/api/greader.php/reader/api/0/subscription/list",
            params={"output": "json"},
            headers={"Authorization": f"GoogleLogin auth={token}"},
            timeout=15,
        )
        list_resp.raise_for_status()
        subs = list_resp.json().get("subscriptions", [])
        return {(s.get("url") or "").strip().rstrip("/") for s in subs if s.get("url")}
    except Exception as exc:
        logger.warning("FreshRSS subscription lookup failed: %s", exc)
        return set()


# ---------------------------------------------------------------------------
# Main collector
# ---------------------------------------------------------------------------


class DirectRSSCollector:
    """
    Fetches RSS feeds directly with browser-grade headers, bypassing FreshRSS.

    Targets DB rows that exist in `sources` but are not subscribed in FreshRSS
    (because FreshRSS rejected them on subscribe). Inserts new articles into
    the `articles` table using the same dedup pipeline as RSSCollector.
    """

    async def collect(self) -> dict[str, Any]:
        start = time.monotonic()
        stats: dict[str, Any] = {
            "feeds_targeted": 0,
            "feeds_succeeded": 0,
            "feeds_failed": 0,
            "articles_found": 0,
            "articles_inserted": 0,
            "articles_skipped_duplicate": 0,
            "collection_time_seconds": 0.0,
        }

        # asyncpg connections are NOT safe under concurrent ops — use a pool
        # sized to MAX_CONCURRENT_FEEDS so each task can acquire its own.
        #
        # Resilience knobs (added 2026-06-05 after the Postgres-restart
        # cascade that wedged all collectors with "connection is closed"
        # errors for ~30 min until the worker was manually recycled):
        #   - setup= runs `SELECT 1` on every checkout. Dead conns raise
        #     immediately and asyncpg replaces them before the caller sees
        #     them.
        #   - max_inactive_connection_lifetime=60 closes idle conns after
        #     60 s so a Postgres restart can leave at most ~60 s of stale
        #     conns in the pool.
        async def _pool_setup(conn: asyncpg.Connection) -> None:
            await conn.fetchval("SELECT 1")

        pool: asyncpg.Pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=MAX_CONCURRENT_FEEDS + 2,
            command_timeout=30,
            setup=_pool_setup,
            max_inactive_connection_lifetime=60,
        )

        try:
            async with httpx.AsyncClient(
                timeout=FEED_FETCH_TIMEOUT,
                follow_redirects=True,
                headers=_browser_headers(),
            ) as freshrss_client:
                subscribed_urls = await _freshrss_subscription_urls(freshrss_client)

            async with pool.acquire() as conn:
                sources = await self._load_orphan_sources(conn, subscribed_urls)
            stats["feeds_targeted"] = len(sources)
            logger.info(
                "DirectRSS: %d orphan sources to fetch (not in FreshRSS)",
                len(sources),
            )

            if not sources:
                stats["collection_time_seconds"] = round(time.monotonic() - start, 2)
                return stats

            sem = asyncio.Semaphore(MAX_CONCURRENT_FEEDS)

            async with TieredFetcher() as fetcher:
                async with httpx.AsyncClient(
                    timeout=FEED_FETCH_TIMEOUT,
                    follow_redirects=True,
                    headers=_browser_headers(),
                ) as client:
                    # return_exceptions=True so one bad source doesn't cancel
                    # siblings and tear down the shared httpx client mid-flight.
                    tasks = [
                        self._collect_one(sem, client, fetcher, pool, src, stats)
                        for src in sources
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for r in results:
                        if isinstance(r, Exception):
                            logger.error("DirectRSS task error: %s", r)

        finally:
            await pool.close()

        stats["collection_time_seconds"] = round(time.monotonic() - start, 2)
        logger.info("DirectRSS collection complete: %s", stats)
        return stats

    # ------------------------------------------------------------------
    # Source loader — orphans only
    # ------------------------------------------------------------------

    async def _load_orphan_sources(
        self, conn: asyncpg.Connection, subscribed_urls: set[str]
    ) -> list[dict[str, Any]]:
        rows = await conn.fetch(
            """
            SELECT id, name, domain, rss_url, source_tier
            FROM sources
            WHERE source_type = 'rss'
              AND is_active = TRUE
              AND health_score > 0.0
              AND rss_url IS NOT NULL
              AND rss_url <> ''
            ORDER BY source_tier ASC, name ASC
            """
        )
        orphans: list[dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            normalised = (d.get("rss_url") or "").strip().rstrip("/")
            if normalised and normalised not in subscribed_urls:
                orphans.append(d)
        return orphans

    # ------------------------------------------------------------------
    # Per-feed processing
    # ------------------------------------------------------------------

    async def _collect_one(
        self,
        sem: asyncio.Semaphore,
        client: httpx.AsyncClient,
        fetcher: TieredFetcher,
        pool: asyncpg.Pool,
        source: dict[str, Any],
        stats: dict[str, Any],
    ) -> None:
        async with sem:
            rss_url = source["rss_url"].strip()
            try:
                resp = await client.get(rss_url)
            except Exception as exc:
                logger.info(
                    "DirectRSS: fetch failed %s: %s", source["name"], exc
                )
                stats["feeds_failed"] += 1
                async with pool.acquire() as conn:
                    await self._mark_failed(conn, str(source["id"]))
                return

            if resp.status_code != 200:
                logger.info(
                    "DirectRSS: %s returned %d", source["name"], resp.status_code
                )
                stats["feeds_failed"] += 1
                async with pool.acquire() as conn:
                    await self._mark_failed(conn, str(source["id"]))
                return

            parsed = feedparser.parse(resp.content)
            entries = list(parsed.entries[:ITEMS_PER_FEED]) if parsed.entries else []
            if not entries:
                # 200 but unparseable — count as failure so health degrades
                logger.info(
                    "DirectRSS: %s returned 200 but no parseable items",
                    source["name"],
                )
                stats["feeds_failed"] += 1
                async with pool.acquire() as conn:
                    await self._mark_failed(conn, str(source["id"]))
                return

            stats["articles_found"] += len(entries)
            inserted_count = 0

            # One pooled connection per source covers all entries serially
            async with pool.acquire() as conn:
                for entry in entries:
                    outcome = await self._process_entry(
                        conn, entry, source, fetcher
                    )
                    if outcome == "inserted":
                        inserted_count += 1
                        stats["articles_inserted"] += 1
                    elif outcome == "duplicate":
                        stats["articles_skipped_duplicate"] += 1

                stats["feeds_succeeded"] += 1
                await self._mark_succeeded(conn, str(source["id"]), inserted_count)
            logger.info(
                "DirectRSS: %s — inserted %d/%d",
                source["name"], inserted_count, len(entries),
            )

    # ------------------------------------------------------------------
    # Per-entry processing
    # ------------------------------------------------------------------

    async def _process_entry(
        self,
        conn: asyncpg.Connection,
        entry: Any,
        source: dict[str, Any],
        fetcher: TieredFetcher,
    ) -> str:
        url_raw = getattr(entry, "link", None) or entry.get("link") if hasattr(entry, "get") else None
        if not url_raw:
            return "skip"
        url = url_raw.strip()
        if not url.startswith(("http://", "https://")):
            return "skip"

        url_hash_v = _url_hash(url)
        existing = await conn.fetchval(
            "SELECT 1 FROM articles WHERE url_hash = $1", url_hash_v
        )
        if existing:
            return "duplicate"

        title = (
            getattr(entry, "title", None)
            or (entry.get("title") if hasattr(entry, "get") else None)
            or url
        )[:500]

        # RSS summary fallback for the tiered fetcher
        rss_summary = ""
        for attr in ("summary", "description", "subtitle"):
            value = getattr(entry, attr, None)
            if value:
                rss_summary = str(value).strip()
                break

        full_text, _tier_used = await fetcher.fetch(
            url=url, domain=_host_from_url(url), rss_summary=rss_summary
        )
        if not full_text or len(full_text) < MIN_FULL_TEXT_CHARS:
            full_text = None
        lead_text = full_text[:LEAD_TEXT_MAX_CHARS] if full_text else None

        # Published timestamp — feedparser exposes parsed struct
        published_at: datetime | None = None
        ts_struct = getattr(entry, "published_parsed", None) or getattr(
            entry, "updated_parsed", None
        )
        if ts_struct:
            try:
                published_at = datetime(*ts_struct[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                published_at = None

        try:
            result = await conn.execute(
                """
                INSERT INTO articles (
                    source_id, url, url_hash, title,
                    lead_text_original, full_text_scraped,
                    published_at, collected_at,
                    content_type, source_tier,
                    nlp_processed
                ) VALUES (
                    $1::uuid, $2, $3, $4,
                    $5, $6,
                    $7, NOW(),
                    'article', $8,
                    FALSE
                )
                ON CONFLICT (url_hash) DO NOTHING
                """,
                str(source["id"]), url, url_hash_v, title,
                lead_text, full_text,
                published_at, int(source["source_tier"]),
            )
            return "inserted" if result.endswith(" 1") else "duplicate"
        except Exception as exc:
            logger.error("DirectRSS DB insert failed for %s: %s", url, exc)
            return "error"

    # ------------------------------------------------------------------
    # Health updates — same shape as RSSCollector for consistency
    # ------------------------------------------------------------------

    async def _mark_succeeded(
        self, conn: asyncpg.Connection, source_id: str, inserted: int
    ) -> None:
        if inserted > 0:
            await conn.execute(
                """
                UPDATE sources
                SET health_score = LEAST(health_score + 0.1, 1.0),
                    consecutive_failures = 0,
                    last_collected_at = NOW()
                WHERE id = $1::uuid
                """,
                source_id,
            )
        else:
            await conn.execute(
                """
                UPDATE sources
                SET last_collected_at = NOW()
                WHERE id = $1::uuid
                """,
                source_id,
            )

    async def _mark_failed(self, conn: asyncpg.Connection, source_id: str) -> None:
        row = await conn.fetchrow(
            """
            UPDATE sources
            SET health_score = GREATEST(health_score - 0.2, 0.1),
                consecutive_failures = consecutive_failures + 1,
                last_collected_at = NOW()
            WHERE id = $1::uuid
            RETURNING name, consecutive_failures
            """,
            source_id,
        )
        # 2026-05-27: only auto-disable after 25 consecutive failures (was 10).
        # Combined with the 0.1 health floor, transient outages no longer
        # permanently kill a source.
        if row and row["consecutive_failures"] >= 25:
            await conn.execute(
                "UPDATE sources SET is_active = FALSE WHERE id = $1::uuid",
                source_id,
            )
            logger.warning(
                "DirectRSS: '%s' auto-disabled after 25 consecutive failures",
                row["name"],
            )


# ---------------------------------------------------------------------------
# CLI entry point — for manual one-shot runs
# ---------------------------------------------------------------------------


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    collector = DirectRSSCollector()
    result = await collector.collect()
    print(result)


if __name__ == "__main__":
    asyncio.run(_main())
