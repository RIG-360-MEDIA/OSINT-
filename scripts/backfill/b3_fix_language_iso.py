"""b3_fix_language_iso.py — fix language_iso using langdetect on the body.

Today both language_detected (from feed/upstream) and language_iso are
unreliable. Many Odia articles get tagged 'ne' (Nepali), Telugu articles
tagged 'en', etc. We saw this in the deep audit.

Strategy:
  1. For each article with substantial full_text_scraped, run langdetect
  2. If detector confidence is high AND result differs from current
     language_iso, UPDATE language_iso
  3. Skip articles with very short bodies (detection unreliable)
  4. Log distribution of changes

Pure Python, no API cost. Runs at ~500 articles/sec on a single core.
"""
from __future__ import annotations

import asyncio
import logging
import sys

sys.path.insert(0, "/app")
from sqlalchemy import text
from backend.database import get_db

# langdetect is non-deterministic; seed for reproducibility
from langdetect import detect_langs, DetectorFactory, LangDetectException
DetectorFactory.seed = 42

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("b3")

BATCH = 1000
MIN_BODY_LEN = 100         # below this, detection unreliable
MIN_CONFIDENCE = 0.85      # only overwrite if detector is confident


def detect(body: str) -> tuple[str | None, float]:
    if not body or len(body) < MIN_BODY_LEN:
        return None, 0.0
    # Use first 2000 chars — faster and more than enough signal
    sample = body[:2000]
    try:
        ranked = detect_langs(sample)
        if not ranked:
            return None, 0.0
        top = ranked[0]
        return top.lang, float(top.prob)
    except LangDetectException:
        return None, 0.0


async def main() -> int:
    total_seen = 0
    total_changed = 0
    total_unchanged = 0
    total_skipped = 0
    changes: dict[str, dict[str, int]] = {}  # old_lang -> new_lang -> count

    while True:
        async with get_db() as db:
            rows = (await db.execute(text("""
                SELECT id::text AS aid, language_iso, full_text_scraped AS body
                  FROM articles
                 WHERE full_text_scraped IS NOT NULL
                   AND substrate_status = 'ok'
                 ORDER BY collected_at DESC
                 LIMIT :lim OFFSET :off
            """), {"lim": BATCH, "off": total_seen})).mappings().all()

        if not rows:
            break

        for r in rows:
            total_seen += 1
            current_lang = r["language_iso"]
            detected_lang, conf = detect(r["body"] or "")
            if detected_lang is None:
                total_skipped += 1
                continue
            if detected_lang == current_lang:
                total_unchanged += 1
                continue
            if conf < MIN_CONFIDENCE:
                total_skipped += 1
                continue

            # Confidence is high and result differs — update
            async with get_db() as db:
                await db.execute(text("""
                    UPDATE articles SET language_iso = :nl WHERE id::text = :id
                """), {"nl": detected_lang, "id": r["aid"]})
                await db.commit()
            total_changed += 1
            changes.setdefault(current_lang or "NULL", {}).setdefault(detected_lang, 0)
            changes[current_lang or "NULL"][detected_lang] += 1

        if total_seen % 5000 == 0:
            log.info("seen=%d changed=%d unchanged=%d skipped=%d",
                     total_seen, total_changed, total_unchanged, total_skipped)

        if len(rows) < BATCH:
            break

    log.info("DONE seen=%d changed=%d unchanged=%d skipped=%d",
             total_seen, total_changed, total_unchanged, total_skipped)
    log.info("CHANGE MATRIX:")
    for old_lang, new_dict in sorted(changes.items(), key=lambda x: -sum(x[1].values())):
        for new_lang, cnt in sorted(new_dict.items(), key=lambda x: -x[1])[:5]:
            log.info("  %s -> %s : %d", old_lang, new_lang, cnt)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
