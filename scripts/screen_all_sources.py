"""
Reliability screen across ALL CareersWave newspaper sources.

For every active source with a careerswave_url: fetch today's PDF, run the
hybrid extractor over the first N pages, and score the per-paper signals that
decide whether the paper is reliable enough to build on:
  - live           today's edition actually downloadable
  - articles       count extracted
  - anchored_pct   share with a tight located snapshot
  - mis_anchor     same-page bbox pairs overlapping >0.5 IoU (cross-article)
  - tiny_pct       anchored crops < 8 KB (sliver / caption-strip crops)
  - lang_ok        majority detected language == declared language
                   (catches Google-translate-mangled / mis-tagged editions)

Results are appended as JSONL to /tmp/source_screen.jsonl (one row per paper,
written incrementally so a crash mid-run keeps partial results).

Run inside rig-backend:  python /tmp/screen_all_sources.py
Env: MAX_PAGES (default 3), LANGS (csv filter, e.g. "en,te"; default all)
"""
from __future__ import annotations

import asyncio
import itertools
import json
import os

OUT = "/tmp/source_screen.jsonl"
MAX_PAGES = int(os.environ.get("MAX_PAGES", "3"))


def _iou(a, b) -> float:
    if len(a) != 4 or len(b) != 4:
        return 0.0
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    ua = (
        max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
        + max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
        - inter
    )
    return inter / ua if ua > 0 else 0.0


def _score(arts: list[dict], declared_lang: str) -> dict:
    n = len(arts)
    anc = [a for a in arts if a.get("clip_anchored")]
    by_page: dict = {}
    for a in anc:
        bb = a.get("bounding_box") or []
        if len(bb) == 4:
            by_page.setdefault(a.get("page_number"), []).append(bb)
    mis = 0
    for boxes in by_page.values():
        for x, y in itertools.combinations(boxes, 2):
            if _iou(x, y) > 0.5:
                mis += 1

    def _kb(a) -> float:
        b = a.get("clipping_image_b64") or ""
        return len(b) * 3 / 4 / 1024

    tiny = sum(1 for a in anc if 0 < _kb(a) < 8)
    langs = [(a.get("detected_language") or "").lower() for a in arts]
    maj = max(set(langs), key=langs.count) if langs else ""
    lang_ok = (maj == (declared_lang or "").lower()) if maj else False
    return {
        "articles": n,
        "anchored": len(anc),
        "anchored_pct": round(100 * len(anc) / n) if n else 0,
        "mis_anchor": mis,
        "tiny": tiny,
        "tiny_pct": round(100 * tiny / len(anc)) if anc else 0,
        "maj_lang": maj,
        "lang_ok": lang_ok,
    }


async def main() -> None:
    from sqlalchemy import text

    from backend.collectors.newspaper_collector import (
        download_pdf_from_url,
        get_pdf_url_from_careerswave,
    )
    from backend.collectors.newspaper_layout.hybrid_pipeline import (
        extract_articles_hybrid,
    )
    from backend.database import get_db

    lang_filter = [s for s in os.environ.get("LANGS", "").split(",") if s]
    async with get_db() as db:
        q = (
            "SELECT id, name, language, careerswave_url FROM newspaper_sources "
            "WHERE is_active AND careerswave_url IS NOT NULL ORDER BY language, name"
        )
        rows = (await db.execute(text(q))).fetchall()

    open(OUT, "w").close()  # truncate
    for r in rows:
        if lang_filter and (r.language or "") not in lang_filter:
            continue
        rec = {"name": r.name, "lang": r.language, "live": False}
        try:
            url = await get_pdf_url_from_careerswave(r.careerswave_url)
            if url and str(url).startswith("http"):
                pdf = f"/tmp/screen_{r.id}.pdf"
                if await download_pdf_from_url(url, pdf):
                    rec["live"] = True
                    arts = await extract_articles_hybrid(
                        pdf, paper_id=str(r.id),
                        language=r.language or "en", max_pages=MAX_PAGES,
                    )
                    rec.update(_score(arts, r.language or "en"))
                    try:
                        os.unlink(pdf)
                    except OSError:
                        pass
        except Exception as exc:  # noqa: BLE001
            rec["error"] = str(exc)[:120]
        with open(OUT, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print("DONE", r.name, rec.get("anchored_pct"), rec.get("lang_ok"), flush=True)

    print("SCREEN_COMPLETE")


if __name__ == "__main__":
    asyncio.run(main())
