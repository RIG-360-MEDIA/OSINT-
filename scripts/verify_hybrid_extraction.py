"""
One-off verification harness for the hardened hybrid newspaper extractor.

Downloads today's edition for one source, runs extract_articles_hybrid over the
first few pages, and dumps a per-article report covering the five quality
fields (headline / subheadline / body / localization / snapshot). Snapshot
crops are written to /tmp/hybrid_out/art_NNN.jpg for visual inspection.

Run INSIDE the rig-backend container (PaddleOCR + Groq keys live there):
    PAPER="Financial Express" MAX_PAGES=3 python /tmp/verify_hybrid_extraction.py
"""
from __future__ import annotations

import asyncio
import base64
import json
import os

OUTDIR = "/tmp/hybrid_out"


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

    paper = os.environ.get("PAPER", "Financial Express")
    max_pages = int(os.environ.get("MAX_PAGES", "3"))
    # Clear OUTDIR so crops/overlays never mix across runs (the shared-dir
    # clobber that made stale crops look like the current paper's output).
    import shutil
    shutil.rmtree(OUTDIR, ignore_errors=True)
    os.makedirs(OUTDIR, exist_ok=True)

    async with get_db() as db:
        row = (
            await db.execute(
                text(
                    "SELECT id, name, language, careerswave_url "
                    "FROM newspaper_sources WHERE name = :n LIMIT 1"
                ),
                {"n": paper},
            )
        ).fetchone()

    if not row:
        print("NO_SOURCE", paper)
        return

    pdf_url = await get_pdf_url_from_careerswave(row.careerswave_url)
    print("PDF_URL", pdf_url)
    if not pdf_url:
        print("NO_PDF_URL")
        return

    pdf_path = f"/tmp/{row.name.replace(' ', '_')}.pdf"
    ok = await download_pdf_from_url(pdf_url, pdf_path)
    print("DOWNLOAD_OK", ok, pdf_path)
    if not ok:
        return

    arts = await extract_articles_hybrid(
        pdf_path,
        paper_id=str(row.id),
        language=row.language or "en",
        max_pages=max_pages,
    )
    print("ARTICLES", len(arts))

    summary: list[dict] = []
    n_text = 0       # text-anchored: located by matching the real headline (TRUSTED)
    n_body = 0       # body-anchored: located by matching body text to OCR (HIGH)
    n_layout = 0     # layout-assigned: geometry-block guess (UNVERIFIED)
    n_none = 0       # unanchored: no location found (NO CROP)
    with_subhead = 0
    with_byline = 0
    with_img = 0
    for i, a in enumerate(arts):
        img_b64 = a.get("clipping_image_b64") or ""
        body = a.get("text") or ""
        src = a.get("clip_source") or "none"
        if src == "text":
            n_text += 1
        elif src == "body":
            n_body += 1
        elif src == "layout":
            n_layout += 1
        else:
            n_none += 1
        if a.get("subheadline"):
            with_subhead += 1
        if a.get("byline"):
            with_byline += 1
        if img_b64:
            with_img += 1
            try:
                with open(f"{OUTDIR}/art_{i:03d}.jpg", "wb") as fh:
                    fh.write(base64.b64decode(img_b64))
            except Exception as exc:  # noqa: BLE001
                print("IMG_WRITE_FAIL", i, exc)
        summary.append(
            {
                "i": i,
                "page": a.get("page_number"),
                "headline": a.get("headline"),
                "subheadline": a.get("subheadline"),
                "byline": a.get("byline"),
                "body_head": body[:300],
                "body_paras": body.count("\n\n") + 1 if body else 0,
                "body_len": len(body),
                "text_source": a.get("text_source"),
                "confidence": a.get("extraction_confidence"),
                "needs_review": a.get("needs_review"),
                "vision_head": (a.get("vision_text") or "")[:300],
                "section": a.get("section"),
                "lang": a.get("detected_language"),
                "anchored": a.get("clip_anchored"),
                "src": src,
                "img_kb": round(len(img_b64) * 3 / 4 / 1024, 1),
                "bbox": [round(x, 1) for x in a.get("bounding_box", [])],
            }
        )

    with open(f"{OUTDIR}/summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)

    _render_page_overlays(pdf_path, arts)

    total = len(arts) or 1
    pct = lambda k: f"{k}/{total} ({round(100 * k / total)}%)"
    print(
        "STATS  "
        f"text-anchored(TRUSTED)={pct(n_text)}  "
        f"body-anchored(HIGH)={pct(n_body)}  "
        f"layout-assigned(UNVERIFIED)={pct(n_layout)}  "
        f"unanchored={pct(n_none)}  "
        f"| subhead={with_subhead}/{total} byline={with_byline}/{total}"
    )
    print(json.dumps(summary[:12], ensure_ascii=False, indent=2))


def _render_page_overlays(pdf_path: str, arts: list[dict]) -> None:
    """Render each page once with every article box drawn in place, so the
    extracted region can be eyeballed against the actual article.

    Colour code:  green = text-anchored (trusted),  red = layout-assigned
    (unverified),  unanchored articles default to the whole page and are NOT
    drawn (they have no real region). Each box is numbered with its article
    index so it cross-references summary.json.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # noqa: BLE001
        print("OVERLAY_SKIP missing PyMuPDF:", exc)
        return

    by_page: dict[int, list[tuple[int, dict]]] = {}
    for i, a in enumerate(arts):
        by_page.setdefault(a.get("page_number") or 1, []).append((i, a))

    doc = fitz.open(pdf_path)
    for page_no, entries in by_page.items():
        if page_no < 1 or page_no > len(doc):
            continue
        page = doc[page_no - 1]
        pw, ph = page.rect.width, page.rect.height
        shape = page.new_shape()
        for idx, a in entries:
            src = a.get("clip_source") or "none"
            box = a.get("bounding_box") or []
            if len(box) < 4 or src == "none":
                continue
            # Skip degenerate full-page boxes (nothing meaningful to show).
            if box[2] - box[0] >= pw * 0.97 and box[3] - box[1] >= ph * 0.97:
                continue
            if src == "text":
                colour = (0.0, 0.7, 0.0)
            elif src == "body":
                colour = (0.0, 0.3, 0.9)
            else:
                colour = (1.0, 0.0, 0.0)
            rect = fitz.Rect(*box)
            shape.draw_rect(rect)
            shape.finish(color=colour, width=4)
            shape.insert_text(
                (rect.x0 + 4, rect.y0 + 22), f"#{idx} {src}",
                fontsize=20, color=colour,
            )
        shape.commit()
        out = f"{OUTDIR}/page_{page_no:02d}_overlay.png"
        # Render at 2.5x so small-box scanned editions (Telugu papers, ~555pt)
        # are legible enough to eyeball each crop against its real article.
        page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5)).save(out)
        print("OVERLAY", out, "(green=text, blue=body, red=layout)")
    doc.close()


if __name__ == "__main__":
    asyncio.run(main())
