#!/usr/bin/env python3
"""
One-time retry script for existing empty articles.

Fetches all articles where lead_text_original IS NULL (from active sources),
runs them through the TieredFetcher, and UPDATEs rows where text is recovered.

Key constraints:
  — Only UPDATEs existing rows (never re-inserts — would break url_hash dedup)
  — Only updates articles where lead_text_original IS NULL (never overwrites)
  — Never modifies url_hash, source_id, or url
  — Max MAX_CONCURRENT fetches running simultaneously (Crawl4AI memory ceiling)
  — One shared TieredFetcher (one shared browser) for the entire run

Runtime: expect 20-40 minutes for ~1,830 articles.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from dataclasses import dataclass, field

# Crawl4AI processes deeply nested DOMs that can exceed Python's default limit
sys.setrecursionlimit(10000)

import asyncpg

# Ensure /app is on the path when executed inside Docker
sys.path.insert(0, "/app")

from backend.collectors.tiered_fetcher import TieredFetcher  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql://rig:rigpassword@rig-postgres:5432/rig",
)

BATCH_SIZE = 20
MAX_CONCURRENT = 3  # reduced from 5 — less stack pressure, avoids RecursionError in deep DOMs
MIN_TEXT_LEN = 100
LEAD_TEXT_MAX_CHARS = 2000
PROGRESS_INTERVAL = 50


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@dataclass
class RetryStats:
    total: int = 0
    recovered: int = 0
    # Maps tier_used → count. -1 = all tiers failed.
    tier_counts: dict[int, int] = field(
        default_factory=lambda: {1: 0, 2: 0, 3: 0, 4: 0, 0: 0, -1: 0}
    )

    def record(self, tier: int, text: str | None) -> None:
        self.total += 1
        self.tier_counts[tier] = self.tier_counts.get(tier, 0) + 1
        if text and len(text) >= MIN_TEXT_LEN:
            self.recovered += 1


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def fetch_empty_articles(conn: asyncpg.Connection) -> list[dict]:
    """Return all empty articles from active sources, newest first."""
    rows = await conn.fetch(
        """
        SELECT a.id, a.url, s.domain
        FROM articles a
        JOIN sources s ON a.source_id = s.id
        WHERE a.lead_text_original IS NULL
          AND s.is_active = TRUE
        ORDER BY a.collected_at DESC
        """
    )
    return [dict(row) for row in rows]


async def update_article(
    conn: asyncpg.Connection,
    article_id: object,
    text: str,
) -> None:
    """
    UPDATE the article's text fields in-place.

    The WHERE clause includes IS NULL as a safety guard:
    if another process already filled the text between our SELECT and this
    UPDATE, we skip rather than overwrite.
    """
    await conn.execute(
        """
        UPDATE articles
        SET lead_text_original = $1,
            full_text_scraped  = $1
        WHERE id = $2
          AND lead_text_original IS NULL
        """,
        text,
        article_id,
    )


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------


def _batches(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


async def process_batch(
    conn: asyncpg.Connection,
    articles: list[dict],
    fetcher: TieredFetcher,
    stats: RetryStats,
    sem: asyncio.Semaphore,
) -> None:
    async def fetch_one(article: dict) -> tuple[dict, str | None, int]:
        async with sem:
            try:
                text, tier = await fetcher.fetch(
                    url=article["url"],
                    domain=article["domain"],
                    rss_summary=None,
                )
                return article, text, tier
            except Exception as exc:
                logger.debug("Fetch failed for %s: %s", article["url"], exc)
                return article, None, -1

    tasks = [fetch_one(a) for a in articles]
    # return_exceptions=True: any exception that escapes fetch_one (e.g. RecursionError
    # from Crawl4AI's DOM processing) is returned as a value instead of crashing the batch
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, BaseException):
            logger.warning("Task failed with %s: %s", type(result).__name__, result)
            stats.record(-1, None)
            continue
        article, text, tier = result
        truncated = text[:LEAD_TEXT_MAX_CHARS] if text else None
        stats.record(tier, truncated)

        if truncated and len(truncated) >= MIN_TEXT_LEN:
            try:
                await update_article(conn, article["id"], truncated)
            except Exception as exc:
                logger.error(
                    "DB update failed for article %s: %s", article["id"], exc
                )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    conn: asyncpg.Connection = await asyncpg.connect(DATABASE_URL)
    stats = RetryStats()
    last_reported = 0

    try:
        articles = await fetch_empty_articles(conn)
        total_count = len(articles)
        logger.info("Found %d empty articles to retry", total_count)

        sem = asyncio.Semaphore(MAX_CONCURRENT)

        async with TieredFetcher() as fetcher:
            for batch in _batches(articles, BATCH_SIZE):
                await process_batch(conn, batch, fetcher, stats, sem)

                if stats.total - last_reported >= PROGRESS_INTERVAL or stats.total == total_count:
                    print(
                        f"Processed {stats.total}/{total_count} — "
                        f"Recovered: {stats.recovered} — "
                        f"Failed: {stats.tier_counts.get(-1, 0)}"
                    )
                    last_reported = stats.total

    finally:
        await conn.close()

    print()
    print("RETRY COMPLETE")
    print("==============")
    print(f"Total attempted:   {stats.total:,}")
    print(f"Tier 1 recovered:  {stats.tier_counts.get(1, 0)} (Trafilatura)")
    print(f"Tier 2 recovered:  {stats.tier_counts.get(2, 0)} (Googlebot)")
    print(f"Tier 3 recovered:  {stats.tier_counts.get(3, 0)} (Crawl4AI)")
    print(f"Tier 4 recovered:  {stats.tier_counts.get(4, 0)} (Archive.ph)")
    print(f"RSS summary used:  {stats.tier_counts.get(0, 0)}")
    print(f"Still empty:       {stats.tier_counts.get(-1, 0)}")
    print(f"Total with text:   {stats.recovered:,}")


if __name__ == "__main__":
    asyncio.run(main())
