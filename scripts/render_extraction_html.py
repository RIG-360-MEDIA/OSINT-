"""
Render a self-contained HTML report of the hybrid newspaper extraction so a
human can judge accuracy: every article, its snapshot, and all extracted fields
(headline / subheadline / byline / section / language / page / localization
source / text source / confidence / needs-review / bbox / OCR body / Vision
summary) on one page. Snapshots are embedded as base64 data URIs so the file
opens anywhere with no server.

Run INSIDE rig-backend:
    PAPER="Financial Express" MAX_PAGES=3 python /tmp/render_extraction_html.py
Writes /tmp/hybrid_out/report.html
"""
from __future__ import annotations

import asyncio
import html
import os

OUT = "/tmp/hybrid_out/report.html"


def _esc(v) -> str:
    return html.escape(str(v if v is not None else ""))


def _badge(label: str, value, kind: str = "") -> str:
    return f'<span class="badge {kind}">{_esc(label)}: {_esc(value)}</span>'


def _card(a: dict, idx: int) -> str:
    src = a.get("clip_source") or "none"
    img_b64 = a.get("clipping_image_b64") or ""
    if img_b64:
        snap = f'<img class="snap" src="data:image/jpeg;base64,{img_b64}" alt="snapshot #{idx}">'
    else:
        snap = '<div class="nosnap">NO SNAPSHOT<br><small>article left unanchored — no confident crop</small></div>'

    conf = a.get("extraction_confidence")
    review = a.get("needs_review")
    src_kind = {"text": "ok", "body": "ok", "none": "bad"}.get(src, "warn")
    txt_src = a.get("text_source") or "—"
    review_badge = (
        '<span class="badge bad">NEEDS REVIEW</span>' if review else
        '<span class="badge ok">verified</span>' if conf is not None else ""
    )
    conf_badge = _badge("confidence", conf, "warn" if (conf is not None and conf < 0.3) else "ok") if conf is not None else ""

    body = a.get("text") or ""
    vision = a.get("vision_text") or ""
    show_vision = vision and vision.strip() != body.strip()

    return f"""
    <div class="card">
      <div class="left">{snap}</div>
      <div class="right">
        <h2>#{idx} &nbsp; {_esc(a.get('headline'))}</h2>
        <div class="badges">
          {_badge("page", a.get("page_number"))}
          {_badge("section", a.get("section") or "—")}
          {_badge("lang", a.get("detected_language") or "—")}
          {_badge("crop", src, src_kind)}
          {_badge("text", txt_src, "ok" if txt_src == "ocr" else "warn")}
          {conf_badge} {review_badge}
        </div>
        {f'<p class="sub"><b>Sub-headline:</b> {_esc(a.get("subheadline"))}</p>' if a.get("subheadline") else ""}
        {f'<p class="by"><b>Byline:</b> {_esc(a.get("byline"))}</p>' if a.get("byline") else ""}
        <div class="bodylabel">BODY TEXT &nbsp;<small>({_esc(txt_src)} — grounded record)</small></div>
        <div class="body">{_esc(body)}</div>
        {f'<details><summary>Vision summary (AI — unverified)</summary><div class="vision">{_esc(vision)}</div></details>' if show_vision else ""}
        <div class="bbox">bbox (pts): {_esc([round(x,1) for x in (a.get("bounding_box") or [])])}</div>
      </div>
    </div>"""


def _stats(arts: list[dict]) -> str:
    n = len(arts)
    by_clip = {}
    by_txt = {}
    review = 0
    for a in arts:
        by_clip[a.get("clip_source") or "none"] = by_clip.get(a.get("clip_source") or "none", 0) + 1
        by_txt[a.get("text_source") or "—"] = by_txt.get(a.get("text_source") or "—", 0) + 1
        if a.get("needs_review"):
            review += 1
    clip = " · ".join(f"{k}={v}" for k, v in sorted(by_clip.items()))
    txt = " · ".join(f"{k}={v}" for k, v in sorted(by_txt.items()))
    return (f"<p class='stats'><b>{n} articles</b> &nbsp;|&nbsp; crop: {_esc(clip)} "
            f"&nbsp;|&nbsp; text: {_esc(txt)} &nbsp;|&nbsp; needs_review: {review}</p>")


_CSS = """
body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#0f1115;color:#e6e6e6}
header{padding:18px 24px;background:#161a22;border-bottom:1px solid #2a2f3a;position:sticky;top:0;z-index:5}
header h1{margin:0 0 6px;font-size:20px}
.stats{margin:0;color:#9aa4b2;font-size:13px}
.card{display:flex;gap:18px;padding:18px 24px;border-bottom:1px solid #21262f;align-items:flex-start}
.left{flex:0 0 360px}
.snap{width:100%;border:1px solid #2a2f3a;border-radius:6px;background:#fff}
.nosnap{width:100%;height:120px;display:flex;flex-direction:column;align-items:center;justify-content:center;
  border:1px dashed #3a4150;border-radius:6px;color:#7a8290;text-align:center}
.right{flex:1;min-width:0}
.right h2{margin:0 0 8px;font-size:18px;line-height:1.3}
.badges{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
.badge{font-size:11px;padding:2px 8px;border-radius:10px;background:#222936;color:#c7d0dc;border:1px solid #2f3744}
.badge.ok{background:#10331f;color:#7ee2a8;border-color:#1c5536}
.badge.warn{background:#33280f;color:#e8c37e;border-color:#553f1c}
.badge.bad{background:#3a1620;color:#f08aa0;border-color:#5a2030}
.sub,.by{margin:4px 0;font-size:14px;color:#c7d0dc}
.bodylabel{margin-top:10px;font-size:11px;letter-spacing:.5px;color:#8a93a2}
.body{background:#0b0d11;border:1px solid #21262f;border-radius:6px;padding:10px;font-size:13.5px;
  line-height:1.5;white-space:pre-wrap;margin-top:4px}
details{margin-top:8px}summary{cursor:pointer;color:#8a93a2;font-size:12px}
.vision{background:#13100b;border:1px solid #2c2415;border-radius:6px;padding:8px;font-size:12.5px;
  color:#d8c9a8;white-space:pre-wrap;margin-top:4px}
.bbox{margin-top:8px;font-size:11px;color:#6b7280;font-family:ui-monospace,monospace}
"""


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
    os.makedirs("/tmp/hybrid_out", exist_ok=True)

    async with get_db() as db:
        row = (await db.execute(
            text("SELECT id,name,language,careerswave_url FROM newspaper_sources WHERE name=:n LIMIT 1"),
            {"n": paper},
        )).fetchone()
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
    print("DOWNLOAD_OK", ok)
    if not ok:
        return

    arts = await extract_articles_hybrid(
        pdf_path, paper_id=str(row.id), language=row.language or "en", max_pages=max_pages
    )
    print("ARTICLES", len(arts))

    cards = "\n".join(_card(a, i) for i, a in enumerate(arts))
    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>{_esc(paper)} — extraction report</title><style>{_CSS}</style></head>
<body><header><h1>{_esc(paper)} &nbsp;<small>({_esc(row.language)})</small> — hybrid extraction</h1>
{_stats(arts)}</header>{cards}</body></html>"""

    out = f"/tmp/hybrid_out/report_{row.name.replace(' ', '_')}.html"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(doc)
    print("REPORT", out, f"({len(doc)//1024} KB)")


if __name__ == "__main__":
    asyncio.run(main())
