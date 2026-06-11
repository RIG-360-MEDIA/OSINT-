"""Diagnose Telugu anchoring: OCR lines, layout boxes, fuzzy scores."""
import json

import fitz
import numpy as np

from backend.collectors.newspaper_layout import clip_locator as CL
from backend.collectors.newspaper_layout.assembler import assemble_articles
from backend.collectors.newspaper_layout.ocr import (
    _DPI, extract_regions, ocr_lines,
)

PDF = "/tmp/Sakshi.pdf"
doc = fitz.open(PDF)
page = doc[0]
zoom = 220 / 72.0
pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB)
img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
L = ocr_lines(img, lang="te")
print("OCR_LINES_220:", len(L))
print("body_h sample heights:", sorted(round(y1 - y0) for (_, _, _, y0, _, y1) in L)[:8])

# Layout boxes
try:
    regions = extract_regions(PDF, lang="en", max_pages=1)
    arts = assemble_articles(regions[:1]) if regions else []
    print("LAYOUT_REGIONS_pg0:", len(regions[0]) if regions else 0,
          "| LAYOUT_ARTICLE_BOXES:", len(arts))
except Exception as e:
    print("LAYOUT_FAIL:", repr(e))

# Fuzzy scores: take headlines from last summary, score vs OCR lines on page 1
d = json.load(open("/tmp/hybrid_out/summary.json"))
heads = [x["headline"] for x in d if x.get("page") == 1][:4]
from backend.collectors.newspaper_layout.clip_locator import OCRLine
lines = [OCRLine(text=t, conf=c, x0=x0, y0=y0, x1=x1, y1=y1) for (t, c, x0, y0, x1, y1) in L]
bh = CL._median_height(lines)
print("median_line_h:", round(bh), "| FUZZY_MATCH thr:", CL._FUZZY_MATCH)
for h in heads:
    scored = sorted(((CL._fuzzy(l.text, h), l.h, l.text) for l in lines), reverse=True)[:3]
    print("HEAD:", h[:40])
    for s, lh, t in scored:
        print("   sim=%.2f h=%d big=%s txt=%s" % (s, round(lh), lh >= bh * 1.1, t[:30]))
