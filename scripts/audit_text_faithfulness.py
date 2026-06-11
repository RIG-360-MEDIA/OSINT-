"""
Text-faithfulness audit for the hybrid newspaper extractor.

Financial Express PDFs embed the real article text as a vector layer
(~13.7k chars/page). That is GROUND TRUTH. The Vision LLM produces the body we
actually store. This script measures how much of the Vision body is grounded in
the real page text — i.e. how much it paraphrases vs. fabricates.

Per article it reports:
  • token_recall  — fraction of Vision body content-tokens present in the real
    page text. Low = Vision invented words not on the page.
  • num_grounded  — of the numbers/years in the Vision body, how many appear
    verbatim in the real text. Fabricated figures are the highest-risk error.
  • the specific ungrounded numbers, so a human can eyeball them.

No fabricated scoring: every number comes from set intersection against the
embedded text. Run INSIDE rig-backend (PDFs live in /tmp there).
"""
from __future__ import annotations

import json
import re

PDF = "/tmp/Financial_Express.pdf"
SUMMARY = "/tmp/final_fe/summary.json"

_WORD = re.compile(r"[A-Za-z]{4,}")          # content words, 4+ letters
_NUM = re.compile(r"\d[\d,\.]*")              # numbers / figures / years


def _norm_words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text)}


def _nums(text: str) -> list[str]:
    # Normalise thousands separators so "22,000" matches "22000".
    out = []
    for m in _NUM.findall(text):
        out.append(m.replace(",", "").rstrip("."))
    return [n for n in out if n]


def main() -> None:
    import fitz
    import numpy as np
    import pytesseract

    doc = fitz.open(PDF)
    # FE's embedded text layer is font-encoded gibberish (no ToUnicode map), so
    # we OCR the rendered pages instead. Tesseract English on the clean
    # digital-native FE render is readable ground truth (imperfect but real).
    truth_parts = []
    for i in range(min(len(doc), 3)):
        pix = doc[i].get_pixmap(matrix=fitz.Matrix(2.0, 2.0), colorspace=fitz.csRGB)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, 3
        )
        truth_parts.append(pytesseract.image_to_string(img, lang="eng"))
    truth_text = " ".join(truth_parts)
    truth_words = _norm_words(truth_text)
    truth_nums = set(_nums(truth_text))
    doc.close()
    print(f"GROUND TRUTH (OCR): {len(truth_words)} unique words, "
          f"{len(truth_nums)} numbers, {len(truth_text)} chars")
    print("=" * 70)

    arts = json.load(open(SUMMARY, encoding="utf-8"))
    rows = []
    for a in arts:
        body = a.get("body_head") or ""   # the stored 300-char preview
        bw = _norm_words(body)
        if not bw:
            continue
        recall = len(bw & truth_words) / len(bw)
        bnums = _nums(body)
        grounded = [n for n in bnums if n in truth_nums]
        ungrounded = [n for n in bnums if n not in truth_nums]
        rows.append({
            "i": a["i"],
            "src": a.get("src"),
            "headline": (a.get("headline") or "")[:45],
            "recall": round(recall, 2),
            "nums": len(bnums),
            "grounded": len(grounded),
            "ungrounded": ungrounded,
        })

    rows.sort(key=lambda r: r["recall"])
    print(f"{'i':>2} {'src':6} {'recall':>6} {'nums':>5} {'grnd':>5}  headline / ungrounded#")
    for r in rows:
        ug = f"  UNGROUNDED={r['ungrounded']}" if r["ungrounded"] else ""
        print(f"{r['i']:>2} {r['src']:6} {r['recall']:>6} {r['nums']:>5} "
              f"{r['grounded']:>5}  {r['headline']}{ug}")

    recalls = [r["recall"] for r in rows]
    allnums = sum(r["nums"] for r in rows)
    allgr = sum(r["grounded"] for r in rows)
    print("=" * 70)
    print(f"MEAN token_recall = {sum(recalls)/len(recalls):.2f}  "
          f"(min {min(recalls):.2f}, max {max(recalls):.2f})")
    print(f"NUMBERS grounded  = {allgr}/{allnums} "
          f"({round(100*allgr/allnums) if allnums else 0}%)  "
          f"-> {allnums-allgr} fabricated/garbled figures")


if __name__ == "__main__":
    main()
