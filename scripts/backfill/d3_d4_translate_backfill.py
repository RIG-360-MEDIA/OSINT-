"""d3_d4_translate_backfill.py — parallel backfill of quote/body translations.

D3: Translate ~18K non-English quotes via Groq (uses same prompt as the
    live translate_pending_quotes task, but runs them all in parallel
    instead of waiting for the 5-min beat schedule).

D4: Translate ~92 Kannada article bodies (smaller, runs after D3).

Concurrency: 8 parallel LLM calls. Batch processing inside each call.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys

sys.path.insert(0, "/app")
from sqlalchemy import text
from backend.database import get_db
from backend.nlp.groq_client import (
    FAST_MODEL,
    GroqCallFailed,
    GroqQuotaExhausted,
    call_groq,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("d3d4")

CONCURRENT = 8
BATCH = 100  # rows per DB fetch

# Same prompt as the live translator (claims_quotes_task._TRANSLATE_SYSTEM)
QUOTE_SYS = (
    "You translate news quotes to natural English. Return STRICT JSON: "
    '{"speaker_en": "...", "text_en": "..."}. For non-English input '
    "(Telugu, Tamil, Bengali, Hindi etc.), translate faithfully — "
    "preserve meaning over literal word order. No prose outside JSON, "
    "no fences."
)

BODY_SYS = (
    "You translate news article bodies to natural English. Return STRICT "
    'JSON: {"text_en": "..."}. Preserve all factual claims, names, '
    "numbers, places. Keep paragraph breaks via \\n\\n. No prose outside "
    "JSON, no fences."
)


async def translate_one_quote(speaker: str, quote: str) -> tuple[str | None, str | None]:
    try:
        raw = await call_groq(
            system=QUOTE_SYS,
            user=f"speaker: {speaker}\ntext: {quote}\n\nReturn the JSON object.",
            task_type="classification",
            model=FAST_MODEL,
            json_response=True,
        )
        parsed = json.loads(raw)
        return (
            (parsed.get("speaker_en") or None),
            (parsed.get("text_en") or None),
        )
    except (GroqCallFailed, GroqQuotaExhausted, json.JSONDecodeError) as e:
        log.warning("quote translate failed: %s", str(e)[:80])
        return None, None


async def translate_one_body(body: str) -> str | None:
    try:
        raw = await call_groq(
            system=BODY_SYS,
            user=f"Translate this article body to English:\n\n{body[:6000]}\n\nReturn the JSON object.",
            task_type="generation",
            model=FAST_MODEL,
            json_response=True,
            max_tokens_override=4500,
        )
        parsed = json.loads(raw)
        return parsed.get("text_en") or None
    except (GroqCallFailed, GroqQuotaExhausted, json.JSONDecodeError) as e:
        log.warning("body translate failed: %s", str(e)[:80])
        return None


async def run_d3_quotes() -> int:
    """Backfill non-English quote translations."""
    sem = asyncio.Semaphore(CONCURRENT)
    total_ok, total_fail = 0, 0
    while True:
        async with get_db() as db:
            rows = (await db.execute(text("""
                SELECT q.id::text AS qid, q.speaker_name, q.quote_text
                  FROM article_quotes q
                  JOIN articles a ON a.id = q.article_id
                 WHERE q.quote_text_en IS NULL
                   AND a.language_iso IS NOT NULL
                   AND a.language_iso <> 'en'
                   AND LENGTH(q.quote_text) >= 20
                 ORDER BY q.extracted_at DESC NULLS LAST
                 LIMIT :lim
            """), {"lim": BATCH})).mappings().all()
        if not rows:
            break

        async def process(r):
            async with sem:
                sp_en, qt_en = await translate_one_quote(
                    r["speaker_name"] or "", r["quote_text"]
                )
                if qt_en:
                    async with get_db() as db:
                        await db.execute(text("""
                            UPDATE article_quotes
                               SET quote_text_en = :qt,
                                   speaker_name_en = COALESCE(:sp, speaker_name_en),
                                   translated_at = NOW()
                             WHERE id::text = :id
                        """), {"qt": qt_en[:1500], "sp": sp_en[:240] if sp_en else None, "id": r["qid"]})
                        await db.commit()
                    return True
                return False

        results = await asyncio.gather(*(process(r) for r in rows))
        total_ok += sum(1 for r in results if r)
        total_fail += sum(1 for r in results if not r)
        log.info("[D3 quotes] batch=%d ok_total=%d fail_total=%d", len(rows), total_ok, total_fail)

    log.info("[D3 DONE] ok=%d fail=%d", total_ok, total_fail)
    return total_ok


async def run_d4_bodies() -> int:
    """Backfill Kannada article body translations."""
    sem = asyncio.Semaphore(CONCURRENT)
    total_ok, total_fail = 0, 0
    while True:
        async with get_db() as db:
            rows = (await db.execute(text("""
                SELECT id::text AS aid, full_text_scraped AS body
                  FROM articles
                 WHERE language_iso = 'kn'
                   AND substrate_status = 'ok'
                   AND LENGTH(COALESCE(full_text_translated, '')) < 500
                   AND LENGTH(COALESCE(full_text_scraped, '')) > 200
                 ORDER BY collected_at DESC
                 LIMIT :lim
            """), {"lim": BATCH})).mappings().all()
        if not rows:
            break

        async def process(r):
            async with sem:
                body_en = await translate_one_body(r["body"])
                if body_en and len(body_en) > 100:
                    async with get_db() as db:
                        await db.execute(text("""
                            UPDATE articles SET full_text_translated = :t WHERE id::text = :id
                        """), {"t": body_en[:8000], "id": r["aid"]})
                        await db.commit()
                    return True
                return False

        results = await asyncio.gather(*(process(r) for r in rows))
        total_ok += sum(1 for r in results if r)
        total_fail += sum(1 for r in results if not r)
        log.info("[D4 bodies] batch=%d ok_total=%d fail_total=%d", len(rows), total_ok, total_fail)

    log.info("[D4 DONE] ok=%d fail=%d", total_ok, total_fail)
    return total_ok


async def main() -> int:
    log.info("D3+D4 translation backfill starting...")
    await run_d3_quotes()
    await run_d4_bodies()
    log.info("ALL DONE")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
