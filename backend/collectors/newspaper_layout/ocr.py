"""
PaddleOCR PP-Structure wrapper for newspaper page images.

PP-Structure does two things in one pass per page:
  1. Layout detection — classifies each region as title / text / figure / table
  2. OCR — reads the text inside each region

This is the right tool for CareersWave PDFs because they are scanned newspaper
images; pdfplumber has no text layer to read. PP-Structure handles both the
column-layout understanding and the OCR without needing custom heuristics.

Model download
--------------
On first instantiation PP-Structure downloads its weights from PaddlePaddle's
CDN (~600 MB total for layout + det + rec models). The Dockerfile pre-bakes them
into the image so containers start without internet access at runtime.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Render resolution. 150 DPI gives ~1240×1754 px for an A4 page — enough for
# clean OCR while keeping per-page memory under 8 MB.
_DPI = 150
_ZOOM = _DPI / 72.0  # PyMuPDF zoom factor (PDF points → pixels)


@dataclass(frozen=True)
class OCRRegion:
    type: str         # 'title' | 'text' | 'figure' | 'table'
    text: str         # OCR text (empty for figures)
    confidence: float # mean confidence across lines, 0–1
    x0: float         # bounding box in image pixels
    y0: float
    x1: float
    y1: float
    page_number: int  # 1-based
    page_width: float # image pixel dimensions
    page_height: float

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def estimated_font_pt(self) -> float:
        """Approximate font size in PDF points from bbox height."""
        return self.height * 72.0 / _DPI


# Per-process engine cache: lang → PPStructure instance.
# Loaded once per worker process; model weights stay in memory.
_ENGINES: dict[str, object] = {}


# PP-Structure layout detection model ships weights only for 'en' and 'ch'.
# For other languages (te, hi, etc.) we use 'en' for layout (visual, language-agnostic)
# while still passing the requested lang to the OCR component.
_LAYOUT_SUPPORTED = ("en", "ch")


def _get_engine(lang: str):
    layout_lang = lang if lang in _LAYOUT_SUPPORTED else "en"
    if layout_lang not in _ENGINES:
        try:
            from paddleocr import PPStructure  # type: ignore[import]
        except ImportError:
            raise ImportError(
                "paddleocr is not installed. Add paddlepaddle>=2.6.0 and "
                "paddleocr>=2.8.0,<3.0 to requirements.txt and rebuild."
            )
        _ENGINES[layout_lang] = PPStructure(
            show_log=False,
            lang=layout_lang,
            layout=True,
            ocr=True,
            table=False,
            recovery=False,
        )
        logger.info("PP-Structure engine ready (layout_lang=%s, requested=%s)", layout_lang, lang)
    return _ENGINES[layout_lang]


def extract_regions(
    pdf_path: str,
    lang: str = "en",
    max_pages: int = 24,
) -> list[list[OCRRegion]]:
    """
    Render each PDF page to an image and run PP-Structure on it.

    Returns one list[OCRRegion] per page (up to max_pages).
    Empty list on any hard failure so callers can fall back gracefully.
    """
    try:
        import fitz          # PyMuPDF — already in requirements
        import numpy as np   # numpy ships with paddleocr anyway
    except ImportError as exc:
        logger.warning("extract_regions: missing dep %s", exc)
        return []

    engine = _get_engine(lang)
    mat = fitz.Matrix(_ZOOM, _ZOOM)

    all_pages: list[list[OCRRegion]] = []
    try:
        doc = fitz.open(pdf_path)
        n = min(len(doc), max_pages)
        for i in range(n):
            page = doc[i]
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
            # frombuffer → (H, W, 3) uint8 without an extra copy
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, 3
            )
            pw, ph = float(pix.width), float(pix.height)
            regions = _process_page(engine, img, i + 1, pw, ph)
            all_pages.append(regions)
            logger.info("PP-Structure page %d/%d: %d regions", i + 1, n, len(regions))
        doc.close()
    except Exception as exc:
        logger.warning("extract_regions failed for %s: %s", pdf_path, exc)

    return all_pages


def _process_page(
    engine,
    img,            # numpy RGB uint8
    page_number: int,
    page_width: float,
    page_height: float,
) -> list[OCRRegion]:
    try:
        raw = engine(img)
    except Exception as exc:
        logger.warning("PP-Structure inference error on page %d: %s", page_number, exc)
        return []

    regions: list[OCRRegion] = []
    for item in raw or []:
        rtype = str(item.get("type") or "text").lower()
        bbox  = item.get("bbox") or []
        if len(bbox) < 4:
            continue

        x0, y0, x1, y1 = (float(v) for v in bbox[:4])
        text, conf = _read_text(item)

        # Skip figures with no text, and zero-area boxes
        if rtype == "figure" and not text:
            continue
        if x1 <= x0 or y1 <= y0:
            continue

        regions.append(OCRRegion(
            type=rtype,
            text=text.strip(),
            confidence=conf,
            x0=x0, y0=y0, x1=x1, y1=y1,
            page_number=page_number,
            page_width=page_width,
            page_height=page_height,
        ))
    return regions


def _read_text(item: dict) -> tuple[str, float]:
    """
    Extract concatenated text and mean confidence from a PP-Structure item.

    PP-Structure returns `res` in different shapes depending on version:
      v2.7+  list of dicts  [{text, confidence, text_region}, ...]
      some   list of tuples [(bbox_pts, (text, score)), ...]
      fallback dict          {text: str}
    """
    res = item.get("res")
    if not res:
        return "", 0.0

    parts: list[str] = []
    scores: list[float] = []

    if isinstance(res, list):
        for r in res:
            if isinstance(r, dict):
                t = str(r.get("text") or "")
                c = float(r.get("confidence") or r.get("score") or 0.0)
            elif isinstance(r, (list, tuple)) and len(r) == 2:
                # (bbox_points, (text, score))
                inner = r[1]
                if isinstance(inner, (list, tuple)) and len(inner) == 2:
                    t, c = str(inner[0]), float(inner[1])
                else:
                    continue
            else:
                continue
            if t:
                parts.append(t)
                scores.append(c)

    elif isinstance(res, dict):
        t = str(res.get("text") or "")
        c = float(res.get("confidence") or 0.0)
        if t:
            parts.append(t)
            scores.append(c)

    text = " ".join(parts)
    conf = sum(scores) / len(scores) if scores else 0.0
    return text, conf
