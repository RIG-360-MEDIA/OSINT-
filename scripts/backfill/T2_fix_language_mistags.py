"""T2_fix_language_mistags.py — Re-detect language on mistagged articles.

Two failure modes from the audit:
  1. language_detected='en' but title contains non-Latin script characters
     (Telugu, Devanagari, Bengali, Tamil, Kannada, Malayalam, etc.).
     For these, the SCRIPT itself disambiguates — no ML needed.
  2. language_detected='te' but title has zero Telugu characters.
     For these, fall back to langdetect on the title.

All updates are backed up to articles_lang_backup_20260523 before running.

Usage:
    docker exec rig-backend python /app/scripts/backfill/T2_fix_language_mistags.py
"""
from __future__ import annotations

import asyncio
import sys
import re

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from backend.database import get_db  # noqa: E402

# Unicode script ranges → ISO-639-1 language code
# Order matters: most-specific first (some scripts overlap with Devanagari)
SCRIPT_TO_LANG: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[ఀ-౿]"), "te"),   # Telugu
    (re.compile(r"[ঀ-৿]"), "bn"),   # Bengali
    (re.compile(r"[஀-௿]"), "ta"),   # Tamil
    (re.compile(r"[ಀ-೿]"), "kn"),   # Kannada
    (re.compile(r"[ഀ-ൿ]"), "ml"),   # Malayalam
    (re.compile(r"[઀-૿]"), "gu"),   # Gujarati
    (re.compile(r"[਀-੿]"), "pa"),   # Gurmukhi (Punjabi)
    (re.compile(r"[ऀ-ॿ]"), "hi"),   # Devanagari (Hindi default)
    (re.compile(r"[؀-ۿ]"), "ur"),   # Arabic/Urdu
]


def detect_from_script(title: str) -> str | None:
    """Return language code if the title clearly contains a single Indic
    script. Returns None if mixed or no Indic script."""
    if not title:
        return None
    matches = []
    for pat, code in SCRIPT_TO_LANG:
        # Count distinct script chars (excluding spaces/digits)
        hits = len(pat.findall(title))
        if hits >= 3:  # at least 3 chars in that script → confident
            matches.append((code, hits))
    if not matches:
        return None
    # Pick the script with the most hits
    matches.sort(key=lambda x: x[1], reverse=True)
    return matches[0][0]


def detect_with_langdetect(title: str) -> str | None:
    """Fallback for te-tagged-but-Latin titles."""
    try:
        from langdetect import detect, DetectorFactory  # noqa: E402
        DetectorFactory.seed = 42  # deterministic
        return detect(title)
    except Exception:
        return None


async def run() -> None:
    fixed_script = 0
    fixed_ml = 0
    no_signal = 0

    async with get_db() as db:
        # Backup
        print("Creating backup table…")
        await db.execute(text("DROP TABLE IF EXISTS articles_lang_backup_20260523"))
        await db.execute(text("""
            CREATE TABLE articles_lang_backup_20260523 AS
            SELECT id, language_detected AS old_lang, title
              FROM articles
             WHERE title IS NOT NULL
               AND (
                 (language_detected='en' AND title ~ '[ఀ-౿ऀ-ॿঀ-৿஀-௿ಀ-೿ഀ-ൿ઀-૿਀-੿]')
                 OR (language_detected='te' AND title !~ '[ఀ-౿]' AND LENGTH(title) > 5)
               )
        """))
        await db.commit()

        row = (await db.execute(text(
            "SELECT COUNT(*) AS n FROM articles_lang_backup_20260523"
        ))).fetchone()
        print(f"Backup contains {row.n} rows")

        # Case 1: en-tagged with Indic script chars
        print("Case 1: en-tagged with non-Latin script in title…")
        rows = (await db.execute(text("""
            SELECT id::text AS aid, title
              FROM articles
             WHERE language_detected='en'
               AND title ~ '[ఀ-౿ऀ-ॿঀ-৿஀-௿ಀ-೿ഀ-ൿ઀-૿਀-੿]'
        """))).fetchall()
        for r in rows:
            lang = detect_from_script(r.title)
            if lang:
                await db.execute(text(
                    "UPDATE articles SET language_detected = :lang WHERE id = CAST(:a AS uuid)"
                ), {"a": r.aid, "lang": lang})
                fixed_script += 1
            else:
                no_signal += 1
        await db.commit()
        print(f"  Updated {fixed_script} rows via script detection")

        # Case 2: te-tagged but no Telugu chars → langdetect on title
        print("Case 2: te-tagged but no Telugu script…")
        rows = (await db.execute(text("""
            SELECT id::text AS aid, title
              FROM articles
             WHERE language_detected='te'
               AND title !~ '[ఀ-౿]'
               AND LENGTH(title) > 5
        """))).fetchall()
        for r in rows:
            lang = detect_with_langdetect(r.title)
            if lang and lang != "te":
                await db.execute(text(
                    "UPDATE articles SET language_detected = :lang WHERE id = CAST(:a AS uuid)"
                ), {"a": r.aid, "lang": lang})
                fixed_ml += 1
        await db.commit()
        print(f"  Updated {fixed_ml} rows via langdetect")

    print()
    print(f"━━━ Summary ━━━")
    print(f"  Script-detected fixes: {fixed_script}")
    print(f"  Langdetect fixes:      {fixed_ml}")
    print(f"  Could not classify:    {no_signal}")
    print(f"  Total fixed:           {fixed_script + fixed_ml}")


if __name__ == "__main__":
    asyncio.run(run())
