"""Diagnose why quote extraction returns zero on a known quote-rich article."""
import asyncio
import json
import sys
from sqlalchemy import text
from backend.database import get_db
from backend.nlp.groq_client import FAST_MODEL, call_groq
from backend.tasks.coverage.claims_quotes_task import (
    _EXTRACTION_SYSTEM,
    _fetch_article,
    _persist,
    _run,
)

# Modi austerity article — clearly quote-rich. From earlier inspection:
ARTICLE_ID = "f7248c7c-0771-4cae-981a-ca90ac04fecb"


async def main() -> None:
    print("=" * 70)
    print("STEP 1: inspect raw article fields")
    print("=" * 70)
    async with get_db() as db:
        row = (
            await db.execute(
                text(
                    """
                    SELECT id::text, title, language_detected,
                           length(COALESCE(full_text_scraped, ''))   AS full_len,
                           length(COALESCE(lead_text_translated, '')) AS led_len,
                           length(COALESCE(lead_text_original, ''))  AS leo_len,
                           claims_extracted, quotes_extracted,
                           LEFT(COALESCE(full_text_scraped,
                                         lead_text_translated,
                                         lead_text_original), 320) AS preview
                    FROM articles
                    WHERE id = :aid
                    """
                ),
                {"aid": ARTICLE_ID},
            )
        ).mappings().first()
    if row is None:
        print("article not found")
        sys.exit(1)
    print(f"title: {row['title']}")
    print(f"language: {row['language_detected']}")
    print(
        f"lengths -> full_text_scraped:{row['full_len']} "
        f"lead_text_translated:{row['led_len']} "
        f"lead_text_original:{row['leo_len']}"
    )
    print(f"claims_extracted={row['claims_extracted']} "
          f"quotes_extracted={row['quotes_extracted']}")
    print(f"body preview: {row['preview']!r}")

    print()
    print("=" * 70)
    print("STEP 2: what _fetch_article returns")
    print("=" * 70)
    fetched = await _fetch_article(ARTICLE_ID)
    if fetched is None:
        print("fetch returned None")
        sys.exit(1)
    print(f"body length passed to Groq: {len(fetched['body'])}")
    print(f"body[:300]: {fetched['body'][:300]!r}")
    print(f"will skip body-too-short? {len(fetched['body']) < 80}")

    if len(fetched["body"]) < 80:
        print(">>> ROOT CAUSE: body too short, extraction never runs Groq. <<<")
        return

    print()
    print("=" * 70)
    print("STEP 3: actually call Groq with the same prompt + params")
    print("=" * 70)
    user_prompt = f"Title: {fetched['title']}\n\nBody:\n{fetched['body']}"
    try:
        raw = await call_groq(
            system=_EXTRACTION_SYSTEM,
            user=user_prompt,
            task_type="rag_response",
            model=FAST_MODEL,
            json_response=True,
        )
        print(f"raw response (first 800 chars):\n{raw[:800]}")
        try:
            parsed = json.loads(raw)
            print(f"parsed.claims count: {len(parsed.get('claims', []))}")
            print(f"parsed.quotes count: {len(parsed.get('quotes', []))}")
            if parsed.get("quotes"):
                print(f"first quote: {json.dumps(parsed['quotes'][0], indent=2)[:400]}")
        except json.JSONDecodeError as exc:
            print(f"JSON parse FAILED: {exc}")
    except Exception as exc:
        print(f"Groq call FAILED: {type(exc).__name__}: {exc}")
        return

    print()
    print("=" * 70)
    print("STEP 4: force a full re-run via _run(force=True) and check rows")
    print("=" * 70)
    result = await _run(ARTICLE_ID, force=True)
    print(f"_run result: {result}")

    async with get_db() as db:
        cnt = (
            await db.execute(
                text("SELECT COUNT(*) FROM article_quotes WHERE article_id = :a"),
                {"a": ARTICLE_ID},
            )
        ).scalar()
    print(f"quote rows in DB after force re-run: {cnt}")


asyncio.run(main())
