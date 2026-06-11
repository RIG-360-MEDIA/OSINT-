"""Vision-only page-composition map for a full edition: every page, what's on it.

No OCR / no snapshots — just the Vision segmenter's per-page articles (headline +
section), so it runs fast across all pages. PDF already on disk (/tmp).

    TIME_PDF=/tmp/Sakshi.pdf TIME_LANG=te python /tmp/_full_page_map.py
"""
from __future__ import annotations

import asyncio
import base64
import io
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PDF = os.environ["TIME_PDF"]
LANG = os.environ.get("TIME_LANG", "en")
MAXP = int(os.environ.get("TIME_PAGES", "40"))
_VZOOM = 96 / 72.0
_CONC = 6


async def main() -> None:
    import fitz
    from PIL import Image

    from backend.collectors.newspaper_layout.vision_segmenter import segment_page
    from backend.nlp.groq_client import groq_manager

    doc = fitz.open(PDF)
    n = min(len(doc), MAXP)
    name = os.path.basename(PDF).replace(".pdf", "")

    # Pre-render all vision images (fast, main thread).
    b64s = []
    for i in range(n):
        pix = doc[i].get_pixmap(matrix=fitz.Matrix(_VZOOM, _VZOOM))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        b64s.append(base64.b64encode(buf.getvalue()).decode("utf-8"))
    doc.close()

    sem = asyncio.Semaphore(_CONC)

    async def seg(i):
        async with sem:
            try:
                return i, await segment_page(b64s[i], groq_manager)
            except Exception as exc:  # noqa: BLE001
                return i, [{"_error": str(exc)}]

    results = dict(await asyncio.gather(*[seg(i) for i in range(n)]))

    print("=" * 80)
    print(f"{name}  ({LANG})  —  {n} pages")
    total = 0
    for i in range(n):
        arts = results.get(i, [])
        arts = [a for a in arts if isinstance(a, dict) and a.get("headline")]
        total += len(arts)
        if not arts:
            print(f"\n  PAGE {i+1:>2}  —  (no articles — likely full-page ad / jump)")
            continue
        secs: dict[str, int] = {}
        for a in arts:
            s = a.get("section") or "—"
            secs[s] = secs.get(s, 0) + 1
        sec_sum = ", ".join(f"{k}×{v}" for k, v in sorted(secs.items(), key=lambda x: -x[1]))
        print(f"\n  PAGE {i+1:>2}  ({len(arts)} articles)  {sec_sum}")
        for a in arts:
            head = " ".join((a.get("headline") or "").split())[:60]
            print(f"      [{(a.get('section') or '—'):<13}] {head}")
    print(f"\n  TOTAL: {total} articles across {n} pages")


if __name__ == "__main__":
    asyncio.run(main())
