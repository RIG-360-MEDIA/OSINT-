"""
Bulk audit of all active RSS sources in the DB.

Tests each rss_url directly and classifies as:
  VALID_RSS   — 200 + XML/RSS content-type (FreshRSS can use this)
  HTML_NOT_RSS — 200 + HTML (wrong URL, redirect, or paywall)
  DEAD         — 404 / 410
  BLOCKED      — 403 / 401 / 429
  TIMEOUT      — connection timeout
  ERROR        — other HTTP error

Writes a summary and marks DEAD sources inactive in the DB.

Run inside the backend container:
  docker exec rig-backend python scripts/audit_rss_sources.py
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, "/app")

import asyncpg
import httpx

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get(
    "DATABASE_URL_SYNC", "postgresql://rig:rigpassword@rig-postgres:5432/rig"
)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RIGSurveillance/1.0; +https://rigsurveillance.com)"}
CONCURRENCY = 20
TIMEOUT = 12

RSS_CONTENT_TYPES = {"application/rss+xml", "application/atom+xml", "application/xml", "text/xml"}


def classify(status: int, content_type: str) -> str:
    ct = content_type.split(";")[0].strip().lower()
    if status == 200:
        if any(rss_ct in ct for rss_ct in RSS_CONTENT_TYPES):
            return "VALID_RSS"
        if "html" in ct:
            return "HTML_NOT_RSS"
        # text/plain or unknown — check if it might be RSS
        return "VALID_RSS"  # optimistic — FreshRSS will validate
    if status in (404, 410, 400):
        return "DEAD"
    if status in (401, 403, 429):
        return "BLOCKED"
    return "ERROR"


async def check_url(client: httpx.AsyncClient, url: str) -> tuple[str, int, str]:
    try:
        r = await client.get(url, timeout=TIMEOUT)
        ct = r.headers.get("content-type", "")
        return classify(r.status_code, ct), r.status_code, ct
    except httpx.TimeoutException:
        return "TIMEOUT", 0, ""
    except Exception as e:
        return "ERROR", 0, str(e)[:60]


async def main() -> None:
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch(
        """
        SELECT id, name, rss_url FROM sources
        WHERE is_active = TRUE
          AND source_type = 'rss'
          AND rss_url IS NOT NULL AND rss_url != ''
        ORDER BY name
        """
    )
    logger.info("Testing %d active RSS sources...\n", len(rows))

    results: dict[str, list[tuple]] = {
        "VALID_RSS": [], "HTML_NOT_RSS": [], "DEAD": [], "BLOCKED": [], "TIMEOUT": [], "ERROR": [],
    }

    sem = asyncio.Semaphore(CONCURRENCY)

    async def bounded_check(row):
        async with sem:
            status, code, ct = await check_url(client, row["rss_url"])
            return row["id"], row["name"], row["rss_url"], status, code, ct

    async with httpx.AsyncClient(
        follow_redirects=True,
        headers=HEADERS,
        timeout=TIMEOUT,
    ) as client:
        tasks = [bounded_check(row) for row in rows]
        done = 0
        for coro in asyncio.as_completed(tasks):
            source_id, name, url, status, code, ct = await coro
            results[status].append((source_id, name, url, code, ct))
            done += 1
            if done % 50 == 0:
                logger.info("  Progress: %d/%d", done, len(rows))

    logger.info("\n══════════════════════════════════════════")
    logger.info("AUDIT RESULTS")
    logger.info("══════════════════════════════════════════")
    for label, items in results.items():
        logger.info("%-14s : %d sources", label, len(items))

    logger.info("\n── VALID RSS (ready to subscribe) ────────")
    for _, name, url, code, _ in sorted(results["VALID_RSS"], key=lambda x: x[1]):
        logger.info("  ✅ %s\n     %s", name, url)

    logger.info("\n── HTML NOT RSS (wrong/redirected URL) ───")
    for _, name, url, code, _ in sorted(results["HTML_NOT_RSS"], key=lambda x: x[1]):
        logger.info("  ⚠️  %s\n     %s", name, url)

    logger.info("\n── BLOCKED (403/401/429) ─────────────────")
    for _, name, url, code, _ in sorted(results["BLOCKED"], key=lambda x: x[1]):
        logger.info("  🔒 [%d] %s", code, name)

    logger.info("\n── DEAD (404/410) ────────────────────────")
    dead_ids = [str(row[0]) for row in results["DEAD"]]
    for _, name, url, code, _ in sorted(results["DEAD"], key=lambda x: x[1]):
        logger.info("  ❌ [%d] %s\n     %s", code, name, url)

    logger.info("\n── TIMEOUT ───────────────────────────────")
    for _, name, url, _, _ in sorted(results["TIMEOUT"], key=lambda x: x[1]):
        logger.info("  ⏱️  %s", name)

    # Mark DEAD sources inactive
    if dead_ids:
        await conn.execute(
            f"""
            UPDATE sources SET is_active = FALSE
            WHERE id = ANY(ARRAY[{','.join(f"'{i}'" for i in dead_ids)}]::uuid[])
            """
        )
        logger.info("\nMarked %d DEAD sources as inactive in DB.", len(dead_ids))

    await conn.close()
    logger.info("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
