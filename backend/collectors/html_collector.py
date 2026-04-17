"""
HTML Collector — collects articles from scrape-type sources that have no
RSS feed by visiting listing pages and extracting article links.

Phase 1: simplified version. Full listing-page intelligence added later.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import asyncpg
import httpx
import trafilatura
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL_SYNC", "postgresql://rig:rigpassword@rig-postgres:5432/rig"
)

LEAD_TEXT_MAX_CHARS = 2000
MIN_FULL_TEXT_CHARS = 50
HTTP_TIMEOUT = 30

# Patterns that suggest a URL is an article rather than a section/index page
_ARTICLE_PATH_PATTERNS = re.compile(
    r"/(?:article|articles|news|story|stories|post|posts|"
    r"\d{4}/\d{2}/\d{2}/|[^/]+-\d{4,})",
    re.IGNORECASE,
)


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode()).hexdigest()


def _looks_like_article_url(href: str, base_domain: str) -> bool:
    try:
        parsed = urlparse(href)
        if parsed.netloc and base_domain not in parsed.netloc:
            return False
        return bool(_ARTICLE_PATH_PATTERNS.search(parsed.path))
    except Exception:
        return False


class HTMLCollector:
    """
    Collects articles from scrape-type sources without RSS feeds.
    Runs every 6 hours via Celery beat.
    """

    async def collect_all(self) -> dict[str, Any]:
        conn: asyncpg.Connection = await asyncpg.connect(DATABASE_URL)
        total_inserted = 0
        sources_processed = 0

        try:
            rows = await conn.fetch(
                """
                SELECT id, name, domain, source_tier
                FROM sources
                WHERE source_type = 'scrape'
                  AND is_active = TRUE
                  AND health_score > 0.0
                ORDER BY source_tier ASC, name ASC
                """
            )

            for row in rows:
                source = dict(row)
                try:
                    count = await self.collect_source(source, conn)
                    total_inserted += count
                    sources_processed += 1
                    if count > 0:
                        await conn.execute(
                            """
                            UPDATE sources
                            SET health_score = LEAST(health_score + 0.1, 1.0),
                                consecutive_failures = 0,
                                last_collected_at = NOW()
                            WHERE id = $1::uuid
                            """,
                            str(source["id"]),
                        )
                except Exception as exc:
                    logger.error("HTML collect failed for %s: %s", source["name"], exc)
                    row_result = await conn.fetchrow(
                        """
                        UPDATE sources
                        SET health_score = GREATEST(health_score - 0.2, 0.0),
                            consecutive_failures = consecutive_failures + 1
                        WHERE id = $1::uuid
                        RETURNING name, consecutive_failures
                        """,
                        str(source["id"]),
                    )
                    if row_result and row_result["consecutive_failures"] >= 10:
                        await conn.execute(
                            "UPDATE sources SET is_active = FALSE WHERE id = $1::uuid",
                            str(source["id"]),
                        )
                        logger.warning(
                            "Source '%s' auto-disabled after 10 failures",
                            source["name"],
                        )
        finally:
            await conn.close()

        return {
            "sources_processed": sources_processed,
            "articles_inserted": total_inserted,
        }

    async def collect_source(
        self, source: dict, conn: asyncpg.Connection | None = None
    ) -> int:
        """
        Fetch the source listing page, extract article URLs, scrape each one.
        Returns count of articles inserted.
        """
        own_conn = False
        if conn is None:
            conn = await asyncpg.connect(DATABASE_URL)
            own_conn = True

        try:
            domain = source["domain"]
            base_url = f"https://{domain}" if not domain.startswith("http") else domain

            async with httpx.AsyncClient(
                timeout=HTTP_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; RIGBot/1.0)"},
            ) as client:
                try:
                    resp = await client.get(base_url)
                    resp.raise_for_status()
                except Exception as exc:
                    logger.warning("Failed to fetch listing page %s: %s", base_url, exc)
                    return 0

                soup = BeautifulSoup(resp.text, "lxml")
                host = urlparse(base_url).netloc

                article_urls: list[str] = []
                seen: set[str] = set()
                for tag in soup.find_all("a", href=True):
                    href = str(tag["href"]).strip()
                    full_url = urljoin(base_url, href)
                    if full_url in seen:
                        continue
                    seen.add(full_url)
                    if _looks_like_article_url(full_url, host):
                        article_urls.append(full_url)

                logger.info(
                    "Source '%s': found %d candidate article URLs",
                    source["name"],
                    len(article_urls),
                )

                inserted = 0
                source_id = str(source["id"])
                source_tier = int(source["source_tier"])

                for url in article_urls[:30]:  # cap per-source per-run
                    url_hash = _url_hash(url)
                    existing = await conn.fetchval(
                        "SELECT 1 FROM articles WHERE url_hash = $1", url_hash
                    )
                    if existing:
                        continue

                    full_text, lead_text, thumbnail, author = (
                        await self._fetch_and_extract(client, url)
                    )

                    title = url.split("/")[-1].replace("-", " ").replace("_", " ")[:200]
                    try:
                        result = await conn.execute(
                            """
                            INSERT INTO articles (
                                source_id, url, url_hash, title,
                                lead_text_original, full_text_scraped,
                                collected_at, content_type, source_tier,
                                thumbnail_url, author_name, nlp_processed
                            ) VALUES (
                                $1::uuid, $2, $3, $4,
                                $5, $6,
                                NOW(), 'article', $7,
                                $8, $9, FALSE
                            )
                            ON CONFLICT (url_hash) DO NOTHING
                            """,
                            source_id, url, url_hash, title,
                            lead_text, full_text,
                            source_tier, thumbnail, author,
                        )
                        if result.endswith(" 1"):
                            inserted += 1
                    except Exception as exc:
                        logger.error("DB insert failed for %s: %s", url, exc)

            return inserted
        finally:
            if own_conn:
                await conn.close()

    async def _fetch_and_extract(
        self, client: httpx.AsyncClient, url: str
    ) -> tuple[str | None, str | None, str | None, str | None]:
        """Returns (full_text, lead_text, thumbnail_url, author_name)."""
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None, None, None, None
            html = resp.text
        except Exception as exc:
            logger.debug("Fetch failed for %s: %s", url, exc)
            return None, None, None, None

        thumbnail: str | None = None
        author: str | None = None
        try:
            soup = BeautifulSoup(html, "lxml")
            for attr in ({"property": "og:image"}, {"name": "twitter:image"}):
                tag = soup.find("meta", attrs=attr)
                if tag and tag.get("content"):
                    thumbnail = str(tag["content"])
                    break
            for attr in ({"name": "author"}, {"name": "article:author"}):
                tag = soup.find("meta", attrs=attr)
                if tag and tag.get("content"):
                    author = str(tag["content"])
                    break
        except Exception:
            pass

        full_text = trafilatura.extract(
            html,
            favor_precision=True,
            include_tables=False,
            include_comments=False,
            include_links=False,
            no_fallback=True,
        )

        if not full_text or len(full_text) < MIN_FULL_TEXT_CHARS:
            logger.info("Short/empty extraction for %s — may be paywalled", url)
            full_text = None

        lead_text = full_text[:LEAD_TEXT_MAX_CHARS] if full_text else None
        return full_text, lead_text, thumbnail, author
