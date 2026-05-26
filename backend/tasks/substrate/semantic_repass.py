"""
Semantic re-pass over articles needing v2 extraction.

Selects articles where extraction_version is NULL or < 2 (i.e. articles
processed with the v1 prompt, plus the bulk that were stamped
`article_type='other'` during the Cloudflare-1010 incident). Their bodies
are already in `full_text_scraped`, so this script doesn't re-fetch — it
just re-runs the Groq extraction and persists the full v2 schema.

Throughput target: similar to substrate runner (~no fetch latency).

Usage (inside rig-backend container):
    python3 -m backend.tasks.substrate.semantic_repass --all
    python3 -m backend.tasks.substrate.semantic_repass --limit 200
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from typing import Any

from sqlalchemy import text

from backend.database import get_db
from backend.nlp.groq_client import GroqCallFailed, GroqQuotaExhausted
from backend.tasks.substrate.run_corpus_pass import (
    _get_extraction_context,
    _persist_claims,
    _persist_events,
    _persist_locations,
    _persist_numbers,
    _persist_quotes,
    _persist_stances,
    groq_semantic,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("semantic_repass")


async def reprocess_one(db, article: dict[str, Any]) -> str:
    """Run v2 Groq enrichment on one article; persist all new fields."""
    aid = article["id"]
    title = article.get("title") or ""
    body = article.get("body") or ""
    lang = article.get("language_iso") or "en"
    if not body or len(body) < 60:
        return "skipped_no_body"

    # Use script-aware context (English vs non-English-with-translation)
    ctx_body, ctx_sys, ctx_max_tok = _get_extraction_context({
        "language_iso": lang,
        "full_text_scraped": body,
    })

    try:
        semantic = await groq_semantic(title, ctx_body, ctx_sys, ctx_max_tok)
    except (GroqCallFailed, GroqQuotaExhausted):
        return "groq_failed"
    if not semantic:
        return "groq_returned_none"

    # Pull all v2 fields
    article_type = semantic.get("article_type") or "other"
    primary_subject = semantic.get("primary_subject")
    summaries = semantic.get("summaries") or {}
    summary_preview = (summaries.get("preview") or "")[:500] or None
    summary_snippet = (summaries.get("snippet") or "")[:1000] or None
    summary_executive = (summaries.get("executive") or "")[:4000] or None
    locations = semantic.get("locations") or []
    events = semantic.get("events") or []
    quotes = semantic.get("quotes") or []
    stances = semantic.get("actor_stances") or []
    claims = semantic.get("claims") or []
    numbers = semantic.get("numbers") or []
    register = semantic.get("register") or {}
    register_style = register.get("rhetorical_style") or None
    register_emotion = register.get("primary_emotion") or None
    register_is_breaking = bool(register.get("is_breaking", False))
    english_translation = (semantic.get("english_translation") or "")[:8000] or None

    # UPDATE articles with all v2 columns
    await db.execute(
        text(
            """
            UPDATE articles
            SET article_type            = :at,
                primary_subject         = COALESCE(:ps, primary_subject),
                summary_preview         = COALESCE(:sp, summary_preview),
                summary_snippet         = COALESCE(:ss, summary_snippet),
                summary_executive       = COALESCE(:se, summary_executive),
                register_style          = COALESCE(:rs, register_style),
                register_emotion        = COALESCE(:re, register_emotion),
                register_is_breaking    = :rb,
                full_text_translated    = COALESCE(:tr, full_text_translated),
                extraction_version      = 3,
                quotes_extracted        = TRUE,
                claims_extracted        = TRUE
            WHERE id = :id
            """
        ),
        {
            "id": aid,
            "at": article_type,
            "ps": primary_subject,
            "sp": summary_preview,
            "ss": summary_snippet,
            "se": summary_executive,
            "rs": register_style,
            "re": register_emotion,
            "rb": register_is_breaking,
            "tr": english_translation,
        },
    )
    await _persist_locations(db, aid, locations)
    await _persist_events(db, aid, events)
    await _persist_quotes(db, aid, quotes)
    await _persist_claims(db, aid, claims)
    await _persist_stances(db, aid, stances)
    await _persist_numbers(db, aid, numbers)
    await db.commit()
    return "ok"


# WHERE clause now picks up ANY v1-or-NULL article — that's the bulk of the
# corpus. Includes the 48K 'other' articles AND the ~9K previously-enriched
# v1 articles. After the re-pass finishes, every ok article will be at v2.
WHERE_V2_NEEDED = (
    "substrate_status = 'ok' "
    "AND (extraction_version IS NULL OR extraction_version < 3) "
    "AND full_text_scraped IS NOT NULL "
    "AND char_length(full_text_scraped) >= 60"
)


async def run(args: argparse.Namespace) -> int:
    sem = asyncio.Semaphore(8)
    counters: dict[str, int] = {}
    started = time.time()

    async with get_db() as db:
        if args.limit:
            total_q = text(
                f"SELECT COUNT(*) FROM ("
                f"  SELECT 1 FROM articles WHERE {WHERE_V2_NEEDED} "
                f"  LIMIT :lim) sub"
            )
            total = (await db.execute(total_q, {"lim": args.limit})).scalar() or 0
        else:
            total_q = text(f"SELECT COUNT(*) FROM articles WHERE {WHERE_V2_NEEDED}")
            total = (await db.execute(total_q)).scalar() or 0

    if total == 0:
        logger.info("nothing to re-process. exit.")
        return 0

    logger.info("semantic-repass v2: %d articles eligible", total)

    fetched_q = text(
        f"""
        SELECT id::text AS id, title, language_iso,
               full_text_scraped AS body
        FROM articles
        WHERE {WHERE_V2_NEEDED}
        ORDER BY collected_at DESC
        LIMIT :batch
        """
    )

    processed = 0
    batch_size = 128

    async def _one(row: dict[str, Any]) -> str:
        async with sem:
            try:
                async with get_db() as db:
                    return await reprocess_one(db, row)
            except Exception as exc:
                logger.exception("error on %s: %s", row["id"], exc)
                return "errors"

    while processed < total:
        async with get_db() as db:
            rows = (
                await db.execute(fetched_q, {"batch": batch_size})
            ).mappings().all()
        if not rows:
            break
        results = await asyncio.gather(*(_one(dict(r)) for r in rows))
        for s in results:
            counters[s] = counters.get(s, 0) + 1
        processed += len(rows)
        # Result set shrinks naturally as articles flip to v2 — re-query
        # from the front each loop.
        if processed % (batch_size * 4) == 0:
            elapsed = time.time() - started
            rate = processed / max(elapsed, 1)
            eta_min = (total - processed) / max(rate, 0.1) / 60
            logger.info(
                "PROGRESS %d/%d · %.1f art/sec · ETA %.0f min · %s",
                processed, total, rate, eta_min, counters,
            )
        if args.limit and processed >= args.limit:
            break

    elapsed = time.time() - started
    logger.info(
        "DONE in %.0f sec (%.1f min) · processed=%d · counters=%s",
        elapsed, elapsed / 60, processed, counters,
    )
    return 0


def main() -> None:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true", help="re-enrich every eligible article")
    g.add_argument("--limit", type=int, help="smoke-test on N articles")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
