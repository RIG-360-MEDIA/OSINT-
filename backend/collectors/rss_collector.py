"""
RSS Collector — reads new articles from FreshRSS via the GReader API,
extracts full text with Trafilatura, and inserts into the articles table.

Precision settings are FIXED and must not be changed:
  favor_precision=True, include_tables=False, include_comments=False,
  include_links=False, no_fallback=True
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlparse

import asyncpg
import httpx
import trafilatura
from bs4 import BeautifulSoup

from backend.collectors.tiered_fetcher import TieredFetcher

logger = logging.getLogger(__name__)

FRESHRSS_URL: str = os.environ.get("FRESHRSS_URL", "http://rig-freshrss:80").rstrip("/")
FRESHRSS_USERNAME: str = os.environ.get("FRESHRSS_USERNAME", "admin")
FRESHRSS_PASSWORD: str = os.environ.get("FRESHRSS_PASSWORD", "")
DATABASE_URL: str = os.environ.get(
    "DATABASE_URL_SYNC", "postgresql://rig:rigpassword@rig-postgres:5432/rig"
)

LEAD_TEXT_MAX_CHARS = 2000
MIN_FULL_TEXT_CHARS = 50
ITEMS_PER_FEED = 20

# ── Per-domain scrape back-off ────────────────────────────────────────────────
#
# Some domains (e.g. communicationstoday.co.in, observed in coverage audit
# 2026-04-28 → defect C-8) consistently return stub HTML to our scraper while
# their RSS feed still ingests fine. Hammering them on every article costs
# 20–30 s of pointless wall-time and floods the logs. We track per-domain
# scrape failures in-process; after _SCRAPE_FAIL_THRESHOLD consecutive
# failures the domain is suppressed for _SCRAPE_BACKOFF_S. RSS-only ingest
# continues — only the full-text scrape is skipped during back-off.
#
# State is per-worker-process: distributed back-off would require Redis.
import time as _time_module
from collections import defaultdict as _defaultdict

_DOMAIN_SCRAPE_FAILS: dict[str, int] = _defaultdict(int)
_DOMAIN_SCRAPE_SKIP_UNTIL: dict[str, float] = {}
_SCRAPE_FAIL_THRESHOLD = 5
_SCRAPE_BACKOFF_S = 3600  # 1 hour


def _should_skip_scrape(domain: str) -> bool:
    until = _DOMAIN_SCRAPE_SKIP_UNTIL.get(domain, 0.0)
    return _time_module.time() < until


def _record_scrape_result(domain: str, success: bool) -> None:
    if success:
        _DOMAIN_SCRAPE_FAILS[domain] = 0
        return
    _DOMAIN_SCRAPE_FAILS[domain] += 1
    if _DOMAIN_SCRAPE_FAILS[domain] >= _SCRAPE_FAIL_THRESHOLD:
        _DOMAIN_SCRAPE_SKIP_UNTIL[domain] = (
            _time_module.time() + _SCRAPE_BACKOFF_S
        )
        logger.warning(
            "Domain %s entered scrape back-off for %ds after %d "
            "consecutive extraction failures",
            domain, _SCRAPE_BACKOFF_S, _DOMAIN_SCRAPE_FAILS[domain],
        )
        _DOMAIN_SCRAPE_FAILS[domain] = 0  # reset counter once back-off armed


# ---------------------------------------------------------------------------
# Pure utilities
# ---------------------------------------------------------------------------

def _url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode()).hexdigest()


def _host_from_domain(domain_str: str) -> str:
    """Strip path and www. from a sources.domain value like '99acres.com/news'."""
    return domain_str.split("/")[0].lower().lstrip("www.")


def _host_from_url(url: str) -> str:
    return urlparse(url.lower()).netloc.lstrip("www.")


def _extract_thumbnail(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    for attr in (
        {"property": "og:image"},
        {"name": "og:image"},
        {"property": "twitter:image"},
        {"name": "twitter:image"},
    ):
        tag = soup.find("meta", attrs=attr)
        if tag and tag.get("content"):
            return str(tag["content"])
    return None


def _extract_author(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    for attr in ({"name": "author"}, {"name": "article:author"}):
        tag = soup.find("meta", attrs=attr)
        if tag and tag.get("content"):
            return str(tag["content"])
    # schema.org Person
    schema_tag = soup.find(attrs={"itemprop": "author"})
    if schema_tag:
        name_tag = schema_tag.find(attrs={"itemprop": "name"})
        text = (name_tag or schema_tag).get_text(strip=True)
        return text or None
    return None


# ---------------------------------------------------------------------------
# GReader API client
# ---------------------------------------------------------------------------

class GReaderClient:
    """Minimal async FreshRSS GReader API client."""

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self._base = base_url
        self._username = username
        self._password = password
        self._client = httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "RIGSurveillance/1.0"},
        )

    async def authenticate(self) -> None:
        resp = await self._client.post(
            f"{self._base}/api/greader.php/accounts/ClientLogin",
            data={"Email": self._username, "Passwd": self._password},
        )
        resp.raise_for_status()
        for line in resp.text.splitlines():
            if line.startswith("Auth="):
                token = line[5:].strip()
                self._client.headers["Authorization"] = f"GoogleLogin auth={token}"
                return
        raise ValueError("GReader ClientLogin: Auth= token not found in response")

    async def get_subscriptions(self) -> list[dict]:
        resp = await self._client.get(
            f"{self._base}/api/greader.php/reader/api/0/subscription/list",
            params={"output": "json"},
        )
        resp.raise_for_status()
        return resp.json().get("subscriptions", [])

    async def get_stream_items(self, stream_id: str, count: int = ITEMS_PER_FEED) -> list[dict]:
        encoded = quote(stream_id, safe="")
        resp = await self._client.get(
            f"{self._base}/api/greader.php/reader/api/0/stream/contents/{encoded}",
            params={"n": count, "xt": "user/-/state/com.google/read", "output": "json"},
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json().get("items", [])

    async def close(self) -> None:
        await self._client.aclose()


# ---------------------------------------------------------------------------
# Main collector
# ---------------------------------------------------------------------------

class RSSCollector:
    """
    Collects articles from all active RSS sources via FreshRSS GReader API.
    """

    async def collect(self) -> dict[str, Any]:
        start = time.monotonic()
        stats: dict[str, Any] = {
            "sources_checked": 0,
            "articles_found": 0,
            "articles_inserted": 0,
            "articles_skipped_duplicate": 0,
            "collection_time_seconds": 0.0,
        }

        greader = GReaderClient(FRESHRSS_URL, FRESHRSS_USERNAME, FRESHRSS_PASSWORD)
        conn: asyncpg.Connection = await asyncpg.connect(DATABASE_URL)

        try:
            await greader.authenticate()

            by_rss_url, by_host = await self._load_sources(conn)
            subscriptions = await greader.get_subscriptions()
            logger.info("FreshRSS subscriptions: %d", len(subscriptions))

            # Accumulate per-source outcomes for batch health update at end
            source_outcomes: dict[str, dict[str, Any]] = {}

            # One shared TieredFetcher (and one shared Crawl4AI browser) for
            # the entire collection run — never create a browser per article.
            async with TieredFetcher() as fetcher:
                for sub in subscriptions:
                    feed_url = (sub.get("url") or "").strip()
                    source = by_rss_url.get(feed_url)
                    if source is None:
                        source = by_host.get(_host_from_url(feed_url))

                    source_id: str | None = str(source["id"]) if source else None
                    source_tier: int = int(source["source_tier"]) if source else 2

                    items = await greader.get_stream_items(sub["id"])
                    stats["sources_checked"] += 1
                    stats["articles_found"] += len(items)

                    inserted_count = 0
                    had_error = False

                    for item in items:
                        outcome = await self._process_item(
                            conn, item, source_id, source_tier, by_host, fetcher
                        )
                        if outcome == "inserted":
                            inserted_count += 1
                            stats["articles_inserted"] += 1
                        elif outcome == "duplicate":
                            stats["articles_skipped_duplicate"] += 1
                        elif outcome == "error":
                            had_error = True

                    if source_id:
                        prior = source_outcomes.get(source_id, {"inserted": 0, "error": False})
                        source_outcomes[source_id] = {
                            "inserted": prior["inserted"] + inserted_count,
                            "error": prior["error"] or (had_error and inserted_count == 0),
                            "name": source["name"] if source else source_id,
                        }

            await self._flush_health_updates(conn, source_outcomes)

        finally:
            await conn.close()
            await greader.close()

        stats["collection_time_seconds"] = round(time.monotonic() - start, 2)
        logger.info("Collection complete: %s", stats)
        return stats

    # ------------------------------------------------------------------
    # Source index (loaded once per collection run — avoids N+1 queries)
    # ------------------------------------------------------------------

    async def _load_sources(
        self, conn: asyncpg.Connection
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        rows = await conn.fetch(
            """
            SELECT id, name, domain, rss_url, source_tier
            FROM sources
            WHERE source_type = 'rss'
              AND rss_url IS NOT NULL
              AND is_active = TRUE
              AND health_score > 0.0
            ORDER BY source_tier ASC, name ASC
            """
        )
        by_rss_url: dict[str, Any] = {}
        by_host: dict[str, Any] = {}
        for row in rows:
            d = dict(row)
            url = (d.get("rss_url") or "").strip()
            if url:
                by_rss_url[url] = d
            host = _host_from_domain(d.get("domain") or "")
            if host:
                by_host[host] = d
        return by_rss_url, by_host

    # ------------------------------------------------------------------
    # Per-item processing
    # ------------------------------------------------------------------

    async def _process_item(
        self,
        conn: asyncpg.Connection,
        item: dict,
        source_id: str | None,
        source_tier: int,
        by_host: dict[str, Any],
        fetcher: TieredFetcher,
    ) -> str:
        canonical = item.get("canonical") or []
        alternate = item.get("alternate") or []
        url_raw = (
            (canonical[0]["href"] if canonical else None)
            or (alternate[0]["href"] if alternate else None)
        )
        if not url_raw:
            return "skip"

        url = url_raw.strip()
        url_hash = _url_hash(url)

        # Resolve source from article URL if not known from feed
        if source_id is None:
            src = by_host.get(_host_from_url(url))
            if src:
                source_id = str(src["id"])
                source_tier = int(src["source_tier"])

        if source_id is None:
            logger.debug("No source match for URL: %s", url)
            return "skip"

        # RSS summary used as last-resort fallback inside the tiered fetcher.
        # GReader API returns summary as {"content": "...", "direction": "ltr"} — extract string.
        _summary_raw = item.get("summary") or item.get("description") or ""
        if isinstance(_summary_raw, dict):
            _summary_raw = _summary_raw.get("content", "")
        rss_summary = (_summary_raw or "").strip()

        # Fetch + extract using tiered fetcher, gated by per-domain back-off (C-8).
        host = _host_from_url(url)
        if _should_skip_scrape(host):
            logger.debug("Skipping scrape for %s (in back-off window)", host)
            full_text = lead_text = thumbnail = author = None
            if rss_summary:
                lead_text = rss_summary[:LEAD_TEXT_MAX_CHARS]
        else:
            try:
                full_text, lead_text, thumbnail, author = await self._fetch_and_extract(
                    url,
                    fetcher=fetcher,
                    domain=host,
                    rss_summary=rss_summary,
                )
                _record_scrape_result(host, success=bool(full_text))
            except Exception as _scrape_exc:
                _record_scrape_result(host, success=False)
                logger.debug("Scrape exception for %s: %s", url, _scrape_exc)
                full_text = lead_text = thumbnail = author = None
                if rss_summary:
                    lead_text = rss_summary[:LEAD_TEXT_MAX_CHARS]

        # Parse published timestamp
        published_at: datetime | None = None
        pub_ts = item.get("published")
        if pub_ts:
            try:
                published_at = datetime.fromtimestamp(int(pub_ts), tz=timezone.utc)
            except (ValueError, OSError):
                pass

        title = (item.get("title") or url)[:500]

        _INSERT_SQL = """
            INSERT INTO articles (
                source_id, url, url_hash, title,
                lead_text_original, full_text_scraped,
                published_at, collected_at,
                content_type, source_tier,
                thumbnail_url, author_name,
                nlp_processed
            ) VALUES (
                $1::uuid, $2, $3, $4,
                $5, $6,
                $7, NOW(),
                'article', $8,
                $9, $10,
                FALSE
            )
            ON CONFLICT (url_hash) DO NOTHING
        """
        _insert_args = (
            source_id, url, url_hash, title,
            lead_text, full_text,
            published_at, source_tier,
            thumbnail, author,
        )

        try:
            result = await conn.execute(_INSERT_SQL, *_insert_args)
            # asyncpg returns "INSERT 0 N" — N=1 means inserted, N=0 means conflict
            return "inserted" if result.endswith(" 1") else "duplicate"
        except (
            asyncpg.exceptions.InterfaceError,
            asyncpg.exceptions.ConnectionDoesNotExistError,
        ) as exc:
            # Stale conn (Postgres restart, idle timeout, network blip).
            # Retry once with a fresh connection — avoids dropping the article.
            # Added 2026-06-05 after the Postgres-restart cascade.
            logger.warning(
                "Stale DB conn — reconnecting to retry insert for %s: %s",
                url, exc,
            )
            try:
                fresh = await asyncpg.connect(DATABASE_URL)
                try:
                    result = await fresh.execute(_INSERT_SQL, *_insert_args)
                    return "inserted" if result.endswith(" 1") else "duplicate"
                finally:
                    await fresh.close()
            except Exception as exc2:
                logger.error(
                    "DB insert failed (after reconnect) for %s: %s",
                    url, exc2,
                )
                return "error"
        except Exception as exc:
            logger.error("DB insert failed for %s: %s", url, exc)
            return "error"

    # ------------------------------------------------------------------
    # HTTP fetch + Trafilatura extraction
    # ------------------------------------------------------------------

    async def _fetch_and_extract(
        self,
        url: str,
        fetcher: TieredFetcher | None = None,
        domain: str = "",
        rss_summary: str = "",
    ) -> tuple[str | None, str | None, str | None, str | None]:
        """
        Returns (full_text, lead_text, thumbnail_url, author_name).

        Does a best-effort quick GET for thumbnail/author metadata, then
        delegates text extraction to the TieredFetcher. The quick GET uses
        a short timeout so JS-rendered sites don't stall the pipeline.
        Trafilatura precision settings are FIXED — do not change them.
        """
        # Quick best-effort fetch for thumbnail + author metadata only.
        # 10s timeout — JS sites return skeleton HTML fast enough for meta tags.
        # Uses rotating browser UA so we don't get fingerprinted-and-banned
        # by sites that block our custom "RIGBot" UA.
        from backend.collectors.direct_rss_collector import _browser_headers
        html: str | None = None
        try:
            async with httpx.AsyncClient(
                timeout=10,
                follow_redirects=True,
                headers=_browser_headers(),
            ) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    html = resp.text
        except Exception as exc:
            logger.debug("Metadata fetch failed for %s: %s", url, exc)

        thumbnail = _extract_thumbnail(html) if html else None
        author = _extract_author(html) if html else None

        # Text extraction via tiered fetcher
        if fetcher is not None:
            text, tier_used = await fetcher.fetch(
                url=url, domain=domain, rss_summary=rss_summary
            )
            if tier_used > 1:
                logger.info("Tier %d used for %s: %.80s", tier_used, domain, url)
        else:
            # Fallback path (no fetcher — should not occur in normal operation)
            text = None
            if html:
                text = trafilatura.extract(
                    html,
                    favor_precision=True,
                    include_tables=False,
                    include_comments=False,
                    include_links=False,
                    no_fallback=True,
                )

        if not text or len(text) < MIN_FULL_TEXT_CHARS:
            text = None

        lead_text = text[:LEAD_TEXT_MAX_CHARS] if text else None
        return text, lead_text, thumbnail, author

    # ------------------------------------------------------------------
    # Batch health update (one UPDATE per source — no N+1)
    # ------------------------------------------------------------------

    async def _flush_health_updates(
        self,
        conn: asyncpg.Connection,
        outcomes: dict[str, dict[str, Any]],
    ) -> None:
        for source_id, outcome in outcomes.items():
            if outcome["inserted"] > 0:
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
            elif outcome["error"]:
                row = await conn.fetchrow(
                    """
                    UPDATE sources
                    SET health_score = GREATEST(health_score - 0.2, 0.1),
                        consecutive_failures = consecutive_failures + 1,
                        last_collected_at = NOW()
                    WHERE id = $1::uuid
                    RETURNING name, consecutive_failures, health_score
                    """,
                    source_id,
                )
                # 2026-05-27: only fully disable a source after 25 consecutive
                # failures (was 10). Combined with the 0.1 health floor, this
                # gives intermittent / transient failures more recovery time.
                if row and row["consecutive_failures"] >= 25:
                    await conn.execute(
                        "UPDATE sources SET is_active = FALSE WHERE id = $1::uuid",
                        source_id,
                    )
                    logger.warning(
                        "Source '%s' auto-disabled after 10 consecutive failures",
                        row["name"],
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
