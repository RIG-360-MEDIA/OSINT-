"""
Test the newspaper_layout PP-Structure pipeline on CareersWave PDFs.

Downloads a PDF from CareersWave, runs PP-Structure layout+OCR,
and prints a summary. No database required.

Requires paddlepaddle + paddleocr installed (available inside rig-backend
container after rebuild; or install locally with:
    pip install paddlepaddle paddleocr)

Usage
-----
    # Default: Telangana Today (en) + Sakshi (te)
    python scripts/test_newspaper_layout.py

    # Single paper
    python scripts/test_newspaper_layout.py --paper sakshi
    python scripts/test_newspaper_layout.py --paper telangana_today

    # Run on a local PDF file you already have
    python scripts/test_newspaper_layout.py --file /path/to/newspaper.pdf --lang en
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")

DIVIDER = "=" * 64

# (display_name, language, careerswave_url)
PAPERS: dict[str, tuple[str, str, str]] = {
    "telangana_today": (
        "Telangana Today", "en",
        "https://www.careerswave.in/telangana-today-epaper-pdf-free-download/",
    ),
    "the_hindu": (
        "The Hindu", "en",
        "https://www.careerswave.in/the-hindu-epaper-pdf-download-for-upsc/",
    ),
    "indian_express": (
        "Indian Express", "en",
        "https://www.careerswave.in/indian-express-epaper-pdf-free-download/",
    ),
    "deccan_chronicle": (
        "Deccan Chronicle", "en",
        "https://www.careerswave.in/deccan-chronicle-epaper-pdf-free-download/",
    ),
    "eenadu": (
        "Eenadu", "te",
        "https://www.careerswave.in/eenadu-epaper-pdf-free-download/",
    ),
    "sakshi": (
        "Sakshi", "te",
        "https://www.careerswave.in/sakshi-epaper-pdf-free-download/",
    ),
    "namaste_telangana": (
        "Namaste Telangana", "te",
        "https://www.careerswave.in/namaste-telangana-epaper-pdf-free-download/",
    ),
    "andhra_jyothi": (
        "Andhra Jyothi", "te",
        "https://www.careerswave.in/andhra-jyothi-epaper-pdf-free-download/",
    ),
}


def _safe(s: str, width: int = 72) -> str:
    """Encode to terminal charset safely (handles Telugu/Devanagari)."""
    enc = sys.stdout.encoding or "utf-8"
    return s[:width].encode(enc, errors="replace").decode(enc)


async def test_from_file(pdf_path: str, lang: str, paper_key: str = "local") -> bool:
    """Run the pipeline on an already-downloaded PDF."""
    from backend.collectors.newspaper_layout.ocr import extract_regions
    from backend.collectors.newspaper_layout.assembler import assemble_articles
    from backend.collectors.newspaper_layout.pipeline import extract_articles_from_pdf

    kb = os.path.getsize(pdf_path) // 1024
    print(f"\n  PDF : {pdf_path}  ({kb:,} KB)  lang={lang}")

    print("\n[1] PP-Structure layout + OCR (first 4 pages) ...")
    try:
        pages = extract_regions(pdf_path, lang=lang, max_pages=4)
    except ImportError:
        print("  [!!] paddleocr not installed.")
        print("       Install with:  pip install paddlepaddle paddleocr")
        print("       Or test inside the rig-backend container after rebuild.")
        return False

    total = sum(len(p) for p in pages)
    print(f"  [OK] {len(pages)} pages, {total} regions detected")

    if pages:
        type_counts: dict[str, int] = {}
        for r in (r for page in pages for r in page):
            type_counts[r.type] = type_counts.get(r.type, 0) + 1
        for rtype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"       {rtype:<20} {count}")

    print("\n[2] Article assembly ...")
    raw = assemble_articles(pages)
    print(f"  [OK] {len(raw)} article candidates")
    if raw:
        avg_body = sum(len(a.get("text", "")) for a in raw) / len(raw)
        conts = sum(1 for a in raw if a.get("continuation_page"))
        print(f"       avg body length : {avg_body:.0f} chars")
        print(f"       continuations   : {conts}")

    print("\n[3] Full pipeline (skip LLM normalization for speed) ...")
    articles = await extract_articles_from_pdf(
        pdf_path,
        paper_id=paper_key,
        language=lang,
        max_pages=4,
        skip_normalization=True,
    )
    print(f"  [OK] {len(articles)} final articles")

    if articles:
        print(f"\n[4] Sample (first 5 of {len(articles)}):")
        for i, a in enumerate(articles[:5], 1):
            hl   = _safe(a.get("headline") or "")
            body = _safe((a.get("text") or "").replace("\n", " "), 90)
            page = a.get("page_number", "?")
            cont = f"-> p{a['continuation_page']}" if a.get("continuation_page") else ""
            print(f"\n  [{i}] page {page} {cont}")
            print(f"       {hl}")
            print(f"       {body}...")

        out = Path(f"/tmp/test_layout_{paper_key}.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        print(f"\n  Full output -> {out}")

    return len(articles) > 0


async def test_paper(key: str) -> bool:
    from backend.collectors.newspaper_collector import (
        get_pdf_url_from_careerswave,
        download_pdf_from_url,
    )

    name, lang, url = PAPERS[key]
    print(f"\n{DIVIDER}")
    print(f"  {name}  ({lang.upper()})  --  {key}")
    print(DIVIDER)

    print(f"\n[1] Resolving PDF URL from CareersWave ...")
    pdf_url = await get_pdf_url_from_careerswave(url)
    if not pdf_url:
        print("  [FAIL]  No PDF found today (upload may be delayed)")
        return False
    print(f"  [OK]  {pdf_url[:88]}...")

    print(f"\n[2] Downloading PDF ...")
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp_path = tmp.name
    tmp.close()
    try:
        ok = await download_pdf_from_url(pdf_url, tmp_path)
        if not ok:
            print("  [FAIL]  Download failed")
            return False
        kb = os.path.getsize(tmp_path) // 1024
        print(f"  [OK]  {kb:,} KB")
        return await test_from_file(tmp_path, lang, key)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--paper", choices=list(PAPERS), default=None,
        help="CareersWave paper key (default: telangana_today + sakshi)",
    )
    parser.add_argument(
        "--file", default=None,
        help="Path to a local PDF file to test directly (skips CareersWave download)",
    )
    parser.add_argument(
        "--lang", default="en",
        help="Language for --file mode (default: en)",
    )
    args = parser.parse_args()

    if args.file:
        ok = await test_from_file(args.file, args.lang)
        sys.exit(0 if ok else 1)

    targets = [args.paper] if args.paper else ["telangana_today", "sakshi"]
    results: dict[str, bool] = {}
    for key in targets:
        results[key] = await test_paper(key)

    print(f"\n{DIVIDER}")
    print("  SUMMARY")
    print(DIVIDER)
    for key, ok in results.items():
        status = "[OK]  pipeline OK" if ok else "[FAIL] no PDF or 0 articles"
        print(f"  {PAPERS[key][0]:<22} {status}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
