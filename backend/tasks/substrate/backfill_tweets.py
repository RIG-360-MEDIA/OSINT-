"""One-shot backfill of tweet content for already-extracted v2 articles.

Walks every article_links row where the outbound URL is a tweet, calls
the free Twitter oEmbed endpoint via enrich_tweets.enrich_tweet, and
stores the content in article_tweets. Idempotent — re-runs only fill in
rows still in 'pending' / error / not_found states by default.

Usage (inside rig-backend container):
    python3 -m backend.tasks.substrate.backfill_tweets               # all v2 articles, skip already-ok
    python3 -m backend.tasks.substrate.backfill_tweets --redo-all    # also re-fetch already-ok rows
    python3 -m backend.tasks.substrate.backfill_tweets --limit 200   # smoke test
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import time

from sqlalchemy import text

from backend.database import get_db
from backend.tasks.substrate.enrich_tweets import enrich_tweet, is_tweet_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("backfill_tweets")

CANDIDATES_QUERY = """
SELECT DISTINCT a.id AS article_id, l.outbound_url AS tweet_url
FROM articles a
JOIN article_links l ON l.article_id = a.id
WHERE a.extraction_version = 2
  AND (l.outbound_domain LIKE '%twitter.com%' OR l.outbound_domain LIKE '%x.com%')
  AND l.outbound_url ~ '/status/[0-9]+'
  AND NOT EXISTS (
    SELECT 1 FROM article_tweets t
    WHERE t.article_id = a.id
      AND t.tweet_id = (regexp_match(l.outbound_url, '/status/([0-9]+)'))[1]
      AND t.fetch_status = 'ok'
  )
ORDER BY a.id
LIMIT :lim OFFSET :off
"""

CANDIDATES_QUERY_REDO = """
SELECT DISTINCT a.id AS article_id, l.outbound_url AS tweet_url
FROM articles a
JOIN article_links l ON l.article_id = a.id
WHERE a.extraction_version = 2
  AND (l.outbound_domain LIKE '%twitter.com%' OR l.outbound_domain LIKE '%x.com%')
  AND l.outbound_url ~ '/status/[0-9]+'
ORDER BY a.id
LIMIT :lim OFFSET :off
"""


async def backfill(
    *, batch: int = 200, limit: int | None = None,
    redo_all: bool = False, per_call_delay: float = 0.4,
) -> None:
    query = CANDIDATES_QUERY_REDO if redo_all else CANDIDATES_QUERY
    counts: dict[str, int] = {
        "ok": 0, "not_found": 0, "private": 0,
        "rate_limited": 0, "error": 0, "skipped": 0,
    }
    seen_pairs: set[tuple[str, str]] = set()
    started = time.time()
    offset = 0
    processed = 0

    while True:
        rows: list[tuple[str, str]] = []
        async with get_db() as db:
            res = await db.execute(
                text(query), {"lim": batch, "off": offset}
            )
            rows = [(str(r[0]), r[1]) for r in res.fetchall()]

        if not rows:
            break

        for article_id, tweet_url in rows:
            if limit is not None and processed >= limit:
                break
            cleaned = (tweet_url or "").split("?")[0].rstrip("/")
            if not is_tweet_url(cleaned):
                counts["skipped"] += 1
                continue
            key = (article_id, cleaned)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)

            async with get_db() as db:
                try:
                    res = await enrich_tweet(
                        db, article_id, cleaned, delay=per_call_delay
                    )
                    await db.commit()
                    status = res.get("fetch_status", "error")
                    counts[status] = counts.get(status, 0) + 1
                except Exception as e:
                    await db.rollback()
                    logger.warning("enrich failed %s %s: %s", article_id, cleaned, e)
                    counts["error"] += 1

            processed += 1
            if processed % 50 == 0:
                elapsed = time.time() - started
                rate = processed / elapsed if elapsed > 0 else 0
                logger.info(
                    "PROGRESS %d processed · %.2f tweets/sec · %s",
                    processed, rate, counts,
                )

        if limit is not None and processed >= limit:
            break
        offset += batch

    total_t = time.time() - started
    logger.info(
        "DONE %d tweets in %.1fs (%.2f/sec) · final=%s",
        processed, total_t,
        processed / total_t if total_t > 0 else 0,
        counts,
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--batch", type=int, default=200)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--redo-all", action="store_true")
    p.add_argument("--delay", type=float, default=0.4)
    args = p.parse_args()

    asyncio.run(
        backfill(
            batch=args.batch,
            limit=args.limit,
            redo_all=args.redo_all,
            per_call_delay=args.delay,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
