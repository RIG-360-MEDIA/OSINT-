"""One-shot byline backfill for v2 articles, using HTML extraction only.

Re-fetches each article's HTML, runs _extract_byline (JSON-LD → meta →
CSS selectors), and UPDATEs articles.byline. No LLM, no Groq quota.

Usage (inside rig-backend container):
    python3 -m backend.tasks.substrate.backfill_bylines              # all v2 articles
    python3 -m backend.tasks.substrate.backfill_bylines --limit 200  # smoke
    python3 -m backend.tasks.substrate.backfill_bylines --concurrency 8
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import time
from typing import Any

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import text

from backend.database import get_db
from backend.tasks.substrate.run_corpus_pass import _extract_byline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backfill_bylines")

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


CANDIDATES_SQL = """
SELECT id, url
FROM articles
WHERE extraction_version IN (2, 3)
  AND byline IS NULL
  AND url IS NOT NULL
ORDER BY id
LIMIT :lim OFFSET :off
"""


async def _fetch_html(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        r = await client.get(url, timeout=12.0, follow_redirects=True)
        if r.status_code != 200:
            return None
        return r.text
    except Exception as e:
        log.debug("fetch failed %s: %s", url, e)
        return None


async def _worker(name: str, client: httpx.AsyncClient, q: asyncio.Queue, counts: dict[str, int]) -> None:
    while True:
        item = await q.get()
        if item is None:
            q.task_done()
            return
        aid, url = item
        try:
            html = await _fetch_html(client, url)
            if not html:
                counts["fetch_failed"] += 1
            else:
                soup = BeautifulSoup(html, "html.parser")
                byline = _extract_byline(soup)
                if byline:
                    async with get_db() as db:
                        await db.execute(
                            text("UPDATE articles SET byline = :b WHERE id = :id"),
                            {"b": byline, "id": aid},
                        )
                        await db.commit()
                    counts["found"] += 1
                else:
                    counts["no_byline"] += 1
        except Exception as e:
            log.warning("worker %s err on %s: %s", name, aid, e)
            counts["error"] += 1
        finally:
            q.task_done()


async def backfill(*, batch: int = 200, limit: int | None = None, concurrency: int = 6) -> None:
    counts = {"found": 0, "no_byline": 0, "fetch_failed": 0, "error": 0}
    started = time.time()
    offset = 0
    processed = 0

    async with httpx.AsyncClient(headers={"User-Agent": UA}) as client:
        q: asyncio.Queue = asyncio.Queue(maxsize=concurrency * 4)
        workers = [
            asyncio.create_task(_worker(f"w{i}", client, q, counts))
            for i in range(concurrency)
        ]
        try:
            while True:
                rows: list[tuple[str, str]] = []
                async with get_db() as db:
                    res = await db.execute(text(CANDIDATES_SQL), {"lim": batch, "off": offset})
                    rows = [(str(r[0]), r[1]) for r in res.fetchall()]
                if not rows:
                    break
                for aid, url in rows:
                    if limit is not None and processed >= limit:
                        break
                    await q.put((aid, url))
                    processed += 1
                    if processed % 100 == 0:
                        elapsed = time.time() - started
                        rate = processed / elapsed if elapsed > 0 else 0
                        log.info(
                            "PROGRESS %d queued · %.1f/sec · %s",
                            processed, rate, counts,
                        )
                if limit is not None and processed >= limit:
                    break
                offset += batch
            await q.join()
        finally:
            for _ in workers:
                await q.put(None)
            await asyncio.gather(*workers, return_exceptions=True)

    total_t = time.time() - started
    rate = processed / total_t if total_t > 0 else 0
    log.info(
        "DONE %d articles in %.1fs (%.1f/sec) · %s",
        processed, total_t, rate, counts,
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--batch", type=int, default=200)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--concurrency", type=int, default=6)
    args = p.parse_args()

    asyncio.run(backfill(batch=args.batch, limit=args.limit, concurrency=args.concurrency))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
