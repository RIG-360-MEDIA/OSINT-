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
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# tessdata_best holds the float LSTM models — markedly more accurate on complex
# scripts (Devanagari/Telugu conjuncts) than the apt "fast" integer models. When
# a best model is present for the language we use it with --oem 1 (LSTM only),
# else fall back to whatever the default tessdata dir has. Path is overridable.
_TESSDATA_BEST_DIR = os.environ.get(
    "TESSDATA_BEST_DIR", "/usr/share/tesseract-ocr/5/tessdata_best"
)

# Languages that use the FAST model even when a best model is present. Latin
# (English) is already clean on the fast model, and best-on-a-large-render is the
# slowest step in the pipeline — so English skips best for a big speed win at no
# measurable quality cost. Complex Indic scripts still require best.
_FAST_PREFERRED = {"eng"}


def _best_tessdata_dir(tess_lang: str) -> str | None:
    """Return the best-models dir if it holds this language, else None."""
    if tess_lang in _FAST_PREFERRED:
        return None
    path = os.path.join(_TESSDATA_BEST_DIR, f"{tess_lang}.traineddata")
    return _TESSDATA_BEST_DIR if os.path.isfile(path) else None

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


# Tesseract language-code mapping (PaddleOCR code → Tesseract lang code).
# Scripts where Tesseract 5 outperforms PaddleOCR on newsprint type. English is
# included: on dense newspaper body type PaddleOCR garbles words ("KIAINDIAIS",
# "atory framewo") while Tesseract `eng` transcribes cleanly — measured on the
# Financial Express front page. Quality of the stored body text is paramount, so
# we prefer Tesseract for the body OCR and keep PaddleOCR only as a fallback.
_TESS_LANG_MAP: dict[str, str] = {
    "en": "eng",
    "te": "tel",
    "hi": "hin",
    "mr": "mar",
    "ta": "tam",
    "kn": "kan",
    "ml": "mal",
    "bn": "ben",
    "gu": "guj",
    "pa": "pan",
}

# Per-process line-OCR engine cache: lang → PaddleOCR instance.
_LINE_ENGINES: dict[str, object] = {}


def _get_line_engine(lang: str):
    """Plain PaddleOCR det+rec engine for line-level text in the page's script.

    PP-Structure's *layout* model ships weights for 'en'/'ch' only, which forced
    Indic pages (te/hi/ta/…) through the English recogniser — producing Latin
    garbage that could not be matched to vision headlines, so no clip box ever
    anchored. The hybrid pipeline only needs per-line text + boxes (not layout
    regions), and PaddleOCR's *recogniser* does support those scripts. Using it
    here sidesteps the en/ch layout limitation entirely.
    """
    if lang not in _LINE_ENGINES:
        try:
            from paddleocr import PaddleOCR  # type: ignore[import]
        except ImportError:
            raise ImportError(
                "paddleocr is not installed. Add paddlepaddle>=2.6.0 and "
                "paddleocr>=2.8.0,<3.0 to requirements.txt and rebuild."
            )
        _LINE_ENGINES[lang] = PaddleOCR(
            show_log=False, lang=lang, use_angle_cls=False
        )
        logger.info("PaddleOCR line engine ready (lang=%s)", lang)
    return _LINE_ENGINES[lang]


def ocr_lines(
    img, lang: str = "en"
) -> list[tuple[str, float, float, float, float, float]]:
    """Return per-line OCR for a page image in its own script.

    Each tuple is (text, confidence, x0, y0, x1, y1) in image pixels. Returns an
    empty list on any failure so callers can fall back gracefully.
    """
    try:
        engine = _get_line_engine(lang)
        res = engine.ocr(img, cls=False)
    except Exception as exc:
        logger.warning("ocr_lines failed (lang=%s): %s", lang, exc)
        return []

    page0 = res[0] if res else []
    out: list[tuple[str, float, float, float, float, float]] = []
    for r in page0 or []:
        try:
            box, (text, conf) = r[0], r[1]
        except (TypeError, ValueError, IndexError):
            continue
        text = str(text or "").strip()
        if not text or not box:
            continue
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        out.append(
            (text, float(conf or 0.0), min(xs), min(ys), max(xs), max(ys))
        )
    return out


def ocr_lines_tesseract(
    img,
    tess_lang: str = "tel",
) -> list[tuple[str, float, float, float, float, float]]:
    """Tesseract 5 word→line OCR for Indic newsprint.

    Groups pytesseract word-level output into logical lines by (block, par, line)
    key. Returns the same tuple format as ocr_lines() so callers are engine-agnostic.
    Tesseract trained on native Telugu newsprint is markedly more accurate than
    PaddleOCR for Telugu newspaper headlines, raising text-anchor recall for the
    hybrid pipeline.
    """
    try:
        import pytesseract  # type: ignore[import]
        from PIL import Image  # type: ignore[import]
        import numpy as np
    except ImportError as exc:
        logger.warning("ocr_lines_tesseract: missing dep %s", exc)
        return []

    try:
        if isinstance(img, np.ndarray):
            pil_img = Image.fromarray(img.astype("uint8"), "RGB")
        else:
            pil_img = img
        best = _best_tessdata_dir(tess_lang)
        if best:
            # Best models are float LSTM → require --oem 1 (legacy is absent).
            config = f"--psm 3 --oem 1 -l {tess_lang} --tessdata-dir {best}"
        else:
            config = f"--psm 3 --oem 3 -l {tess_lang}"
        data = pytesseract.image_to_data(
            pil_img, config=config, output_type=pytesseract.Output.DICT
        )
    except Exception as exc:
        logger.warning("ocr_lines_tesseract failed (lang=%s): %s", tess_lang, exc)
        return []

    line_map: dict[tuple, dict] = {}
    for i in range(len(data.get("text", []))):
        word = str(data["text"][i] or "").strip()
        conf_raw = data["conf"][i]
        if not word or conf_raw == -1:
            continue
        key = (
            int(data["block_num"][i]),
            int(data["par_num"][i]),
            int(data["line_num"][i]),
        )
        if key not in line_map:
            line_map[key] = {
                "words": [], "confs": [],
                "x0": float("inf"), "y0": float("inf"),
                "x1": float("-inf"), "y1": float("-inf"),
            }
        entry = line_map[key]
        entry["words"].append(word)
        entry["confs"].append(float(conf_raw) / 100.0)
        x = float(data["left"][i])
        y = float(data["top"][i])
        w = float(data["width"][i])
        h = float(data["height"][i])
        entry["x0"] = min(entry["x0"], x)
        entry["y0"] = min(entry["y0"], y)
        entry["x1"] = max(entry["x1"], x + w)
        entry["y1"] = max(entry["y1"], y + h)

    out: list[tuple[str, float, float, float, float, float]] = []
    for entry in line_map.values():
        if not entry["words"]:
            continue
        text = " ".join(entry["words"])
        conf = sum(entry["confs"]) / len(entry["confs"])
        if entry["x1"] > entry["x0"] and entry["y1"] > entry["y0"]:
            out.append(
                (text, conf, entry["x0"], entry["y0"], entry["x1"], entry["y1"])
            )
    return out


def ocr_lines_best(
    img,
    lang: str = "en",
) -> list[tuple[str, float, float, float, float, float]]:
    """Return the best line OCR for the given script.

    For Indic scripts, prefer Tesseract 5 (trained on native newsprint) over
    PaddleOCR. Falls back to PaddleOCR if Tesseract fails or its lang pack is
    absent so the pipeline degrades gracefully on containers without the pack.
    """
    if lang in _TESS_LANG_MAP:
        tess_lang = _TESS_LANG_MAP[lang]
        lines = ocr_lines_tesseract(img, tess_lang=tess_lang)
        if lines:
            logger.debug(
                "ocr_lines_best: tesseract/%s → %d lines", tess_lang, len(lines)
            )
            return lines
        logger.info(
            "ocr_lines_best: tesseract/%s empty/failed, falling back to PaddleOCR",
            tess_lang,
        )
    return ocr_lines(img, lang=lang)


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
