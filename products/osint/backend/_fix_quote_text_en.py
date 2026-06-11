"""
One-off fix: populate quote_text_en for two AP story clusters.

  Grievance redressal platform (Andhra CM)  — 88 articles, 84 quotes
  South Coast Railway, Visakhapatnam        — 35 articles, 37 quotes

Strategy:
  - English quotes  → copy quote_text verbatim (no API call)
  - Telugu quotes   → Google Translate (free endpoint, same as i18n.py),
                       writes to analytics.text_en cache on the way through

Run inside osint-backend (DEFAULT .env, NOT --env-file .env.prod):
    docker cp products/osint/backend/_fix_quote_text_en.py osint-backend:/app/
    docker exec -w /app osint-backend python _fix_quote_text_en.py
    docker exec osint-backend rm -f /app/_fix_quote_text_en.py
"""
from __future__ import annotations

import asyncio
import hashlib

import httpx
from sqlalchemy import text as _sql
from sqlalchemy.ext.asyncio import create_async_engine

from config import load_settings

STORY_IDS = [
    "e8a5d010-d67e-407b-a528-ab89e5a39bc2",  # Grievance platform
    "6e5caf49-25ed-4e73-a786-1f5d38c9f18e",  # Railway Vizag
]

_GT = "https://translate.googleapis.com/translate_a/single"


def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


async def _translate(client: httpx.AsyncClient, q: str) -> str | None:
    try:
        r = await client.get(
            _GT,
            params={"client": "gtx", "sl": "auto", "tl": "en", "dt": "t", "q": q[:4800]},
            timeout=8.0,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        return "".join(seg[0] for seg in data[0] if seg and seg[0]).strip() or None
    except Exception:
        return None


async def main() -> None:
    s = load_settings()
    engine = create_async_engine(s.db_url, pool_size=2, max_overflow=0, pool_pre_ping=True, future=True)

    async with engine.connect() as db:
        rows = (await db.execute(_sql("""
            SELECT sq.id, sq.quote_text, a.language_iso
            FROM   analytics.story_quotes sq
            JOIN   articles a ON a.id = sq.article_id
            WHERE  sq.story_id = ANY(:ids)
              AND  sq.quote_text_en IS NULL
              AND  sq.quote_text IS NOT NULL
        """), {"ids": STORY_IDS})).fetchall()

        print(f"Quotes with missing quote_text_en: {len(rows)}")

        english: list[tuple[int, str]] = []
        non_english: list[tuple[int, str]] = []

        for row in rows:
            (english if row.language_iso == "en" else non_english).append((row.id, row.quote_text))

        print(f"  English (direct copy): {len(english)}")
        print(f"  Telugu  (translate):   {len(non_english)}")

        # ── Part 1: English — copy verbatim ──────────────────────────────────
        for qid, text in english:
            await db.execute(_sql("""
                UPDATE analytics.story_quotes
                SET    quote_text_en = :text
                WHERE  id = :id AND quote_text_en IS NULL
            """), {"id": qid, "text": text})
        await db.commit()
        print(f"  ✓ Copied {len(english)} English quotes")

        # ── Part 2: Telugu — translate + cache ───────────────────────────────
        if not non_english:
            print("No Telugu quotes to translate.")
            await engine.dispose()
            return

        unique_texts = {text for _, text in non_english}
        hashes = {t: _md5(t) for t in unique_texts}

        cached = {
            r.src_hash: r.text_en
            for r in (await db.execute(_sql(
                "SELECT src_hash, text_en FROM analytics.text_en WHERE src_hash = ANY(:h)"
            ), {"h": list(hashes.values())})).fetchall()
        }

        translated: dict[str, str] = {t: cached[h] for t, h in hashes.items() if h in cached}
        to_translate = [t for t in unique_texts if t not in translated]
        print(f"  Cache hits: {len(translated)}  |  Need API: {len(to_translate)}")

        sem = asyncio.Semaphore(10)  # max 10 concurrent Google calls

        async def _translate_and_cache(client: httpx.AsyncClient, text: str) -> tuple[str, str | None]:
            async with sem:
                en = await _translate(client, text)
            return text, en

        async with httpx.AsyncClient() as client:
            results = await asyncio.gather(
                *[_translate_and_cache(client, t) for t in to_translate]
            )

        for text, en in results:
            status = "OK  " if en else "FAIL"
            print(f"  {status} {text[:70]!r}")
            if en:
                translated[text] = en
                await db.execute(_sql("""
                    INSERT INTO analytics.text_en (src_hash, text_en)
                    VALUES (:h, :e)
                    ON CONFLICT (src_hash) DO NOTHING
                """), {"h": hashes[text], "e": en})
        await db.commit()  # flush all cache inserts in one shot

        updated = 0
        for qid, text in non_english:
            en = translated.get(text)
            if en:
                await db.execute(_sql("""
                    UPDATE analytics.story_quotes
                    SET    quote_text_en = :en
                    WHERE  id = :id AND quote_text_en IS NULL
                """), {"id": qid, "en": en})
                updated += 1

        await db.commit()
        print(f"  ✓ Translated and saved {updated}/{len(non_english)} Telugu quotes")

    await engine.dispose()
    print("\nDone. Verify:")
    print("  SELECT count(*), count(quote_text_en) FROM analytics.story_quotes")
    print(f"  WHERE story_id = ANY(ARRAY{STORY_IDS!r})")


if __name__ == "__main__":
    asyncio.run(main())
