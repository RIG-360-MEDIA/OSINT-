"""b1_b5_char_offset_and_context.py — populate char_offset_start/end + context on article_quotes.

For each quote where char_offset_start IS NULL OR context IS NULL:
  1. Fetch the parent article's full_text_scraped
  2. Find quote_text inside the body (with fallbacks)
  3. If found, write char_offset_start, char_offset_end, and a 200-char context window
  4. If not found, leave NULL (extraction may have lightly normalized the quote)

Runs in batches of 1000, commits after each batch.
"""
from __future__ import annotations

import asyncio
import logging
import sys

sys.path.insert(0, "/app")
from sqlalchemy import text
from backend.database import get_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("b1b5")

BATCH = 1000
CONTEXT_PAD = 80  # chars on each side


def _find_in_body(body: str, quote: str) -> int:
    """Try several strategies to locate the quote in the body."""
    if not body or not quote:
        return -1
    # Strategy 1: exact match
    idx = body.find(quote)
    if idx >= 0:
        return idx
    # Strategy 2: with curly-quote normalization
    norm_body = body.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    norm_quote = quote.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    idx = norm_body.find(norm_quote)
    if idx >= 0:
        return idx
    # Strategy 3: case-insensitive match on first 60 chars (truncated quote)
    needle = quote[:60].lower()
    hay = body.lower()
    idx = hay.find(needle)
    return idx


async def main() -> int:
    total_updated, total_found, total_missed, batches = 0, 0, 0, 0

    while True:
        async with get_db() as db:
            rows = (await db.execute(text("""
                SELECT q.id::text AS qid,
                       q.quote_text,
                       a.full_text_scraped AS body
                  FROM article_quotes q
                  JOIN articles a ON a.id = q.article_id
                 WHERE (q.char_offset_start IS NULL OR q.context IS NULL)
                   AND q.quote_text IS NOT NULL
                   AND a.full_text_scraped IS NOT NULL
                   AND LENGTH(q.quote_text) >= 10
                 LIMIT :lim
            """), {"lim": BATCH})).mappings().all()

        if not rows:
            break

        for r in rows:
            body = r["body"] or ""
            quote = r["quote_text"] or ""
            idx = _find_in_body(body, quote)
            if idx < 0:
                total_missed += 1
                continue
            end = idx + len(quote)
            ctx_start = max(0, idx - CONTEXT_PAD)
            ctx_end = min(len(body), end + CONTEXT_PAD)
            ctx = body[ctx_start:ctx_end]
            async with get_db() as db:
                await db.execute(text("""
                    UPDATE article_quotes
                       SET char_offset_start = :s,
                           char_offset_end   = :e,
                           context           = :c
                     WHERE id::text = :id
                """), {"s": idx, "e": end, "c": ctx[:500], "id": r["qid"]})
                await db.commit()
            total_found += 1
            total_updated += 1

        batches += 1
        if batches % 5 == 0 or len(rows) < BATCH:
            log.info("processed %d batches · found=%d missed=%d updated=%d",
                     batches, total_found, total_missed, total_updated)
        if len(rows) < BATCH:
            break

    log.info("DONE · batches=%d found=%d missed=%d updated=%d", batches, total_found, total_missed, total_updated)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
