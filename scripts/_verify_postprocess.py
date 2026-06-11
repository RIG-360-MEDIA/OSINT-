"""Run full FE edition through the pipeline; report notice/dupe/section fixes."""
import asyncio
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from backend.collectors.newspaper_layout.hybrid_pipeline import extract_articles_hybrid

PAPER = os.environ.get("PAPER", "Financial Express")
PAGES = int(os.environ.get("TIME_PAGES", "30"))


async def _get_pdf() -> tuple[str, str]:
    from sqlalchemy import text
    from backend.collectors.newspaper_collector import (
        download_pdf_from_url, get_pdf_url_from_careerswave,
    )
    from backend.database import get_db
    async with get_db() as db:
        row = (await db.execute(
            text("SELECT name,language,careerswave_url FROM newspaper_sources WHERE name=:n LIMIT 1"),
            {"n": PAPER})).fetchone()
    url = await get_pdf_url_from_careerswave(row.careerswave_url)
    path = f"/tmp/{row.name.replace(' ', '_')}.pdf"
    await download_pdf_from_url(url, path)
    return path, (row.language or "en")


async def main() -> None:
    PDF, LANG = await _get_pdf()
    arts = await extract_articles_hybrid(PDF, language=LANG, max_pages=PAGES,
                                         with_clip_images=False)
    n = len(arts)
    notices = [a for a in arts if a.get("is_notice")]
    dupes = [a for a in arts if a.get("is_duplicate")]
    clean = [a for a in arts if not a.get("is_notice") and not a.get("is_duplicate")]
    secs = {}
    for a in clean:
        secs[a["section"]] = secs.get(a["section"], 0) + 1
    print(f"TOTAL {n}  |  notices {len(notices)}  |  duplicates {len(dupes)}  "
          f"|  clean news {len(clean)}")
    print("clean-news sections:", dict(sorted(secs.items(), key=lambda x: -x[1])))
    print("\nsample NOTICES flagged:")
    for a in notices[:6]:
        print(f"   p{a['page_number']:>2} {a['headline'][:55]}")
    print("\nsample DUPLICATES flagged:")
    for a in dupes[:6]:
        print(f"   p{a['page_number']:>2} (dup of p{a['duplicate_of']}) {a['headline'][:45]}")
    # any non-canonical section labels left?
    bad = {a["section"] for a in arts} - {
        "Politics", "Business", "Economy", "Sports", "National",
        "International", "Local", "Opinion", "Other",
    }
    print("\nnon-canonical sections remaining:", bad or "none")


if __name__ == "__main__":
    asyncio.run(main())
