"""Time the parallel hybrid pipeline: wall time + per-page for one paper."""
import asyncio
import os
import time

from backend.collectors.newspaper_layout.hybrid_pipeline import (
    extract_articles_hybrid,
    _PAGE_CONCURRENCY,
)

PDF = os.environ.get("TIME_PDF", "/tmp/Financial_Express.pdf")
LANG = os.environ.get("TIME_LANG", "en")
PAGES = int(os.environ.get("TIME_PAGES", "3"))


async def main() -> None:
    print(f"concurrency={_PAGE_CONCURRENCY} pdf={PDF} pages={PAGES}")
    t = time.time()
    arts = await extract_articles_hybrid(PDF, language=LANG, max_pages=PAGES)
    dt = time.time() - t
    print(f"PARALLEL: {dt:.1f}s total | {len(arts)} articles | {dt/PAGES:.1f}s/page")


if __name__ == "__main__":
    asyncio.run(main())
