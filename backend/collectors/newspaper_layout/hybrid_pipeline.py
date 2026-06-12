"""
Hybrid newspaper extraction: Vision segmentation + located clip boxes.

Pipeline per page:
  1. Render at OCR DPI -> PaddleOCR (paper's own script) -> per-line pixel boxes.
  2. Render at vision DPI -> Groq Vision -> articles (headline/subheadline/body/...).
  3. Locate each article's clip box by:
     a. TEXT anchor: match its headline (then subheadline) to the OCR lines
        (clip_locator). Works well for Latin; fuzzier for Indic display type.
     b. LAYOUT anchor (fallback): when text fails, assign a PP-Structure layout
        region box by reading-order position. The layout model is visual and
        language-agnostic, so it localises articles whose script OCRs poorly.
  4. Guard: drop sliver crops and de-duplicate nested / overlapping boxes so a
     loose match can never emit a confidently-wrong snapshot.

Vision supplies *what* the articles are; OCR + layout supply *where* they sit.
bounding_box is in PDF points [left, top, right, bottom] (top-down Y).
"""
from __future__ import annotations

import asyncio
import base64
import io
import itertools
import logging
import os
import re

# Keep each Tesseract subprocess single-threaded so N pages OCR'd concurrently
# (one per core) don't oversubscribe via OpenMP. Set before pytesseract spawns.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

# Pages processed concurrently. OCR (Tesseract subprocess, releases the GIL) is
# the bottleneck, so this scales with cores; capped to avoid memory blow-up and
# Vision-API rate pressure.
_PAGE_CONCURRENCY = max(1, min(6, (os.cpu_count() or 4)))

from .clip_locator import OCRLine, locate_clip_box, locate_clip_box_by_body
from .ocr import ocr_lines, ocr_lines_best
from .postprocess import is_notice, mark_duplicates
from .vision_segmenter import segment_page

logger = logging.getLogger(__name__)

# OCR render DPI floor. Higher than the 150 used for layout: stylised display
# headlines (esp. Telugu/Indic banners) only recognise well at finer detail,
# which is what the clip anchor matches against. This is a FLOOR — when the
# page embeds a higher-resolution scan we render at the scan's native pixels
# instead (see `_ocr_zoom_for_page`), so we never downsample the source before
# OCR. Scanned Indic editions (Sakshi/Andhra Jyothi) embed ~2300px JPEGs in a
# ~555pt box; a fixed 220 DPI would render only ~1700px and throw away ~27% of
# the available detail, starving the Telugu OCR.
_OCR_DPI = 220
_OCR_ZOOM = _OCR_DPI / 72.0
# Cap so a pathologically large embedded image can't blow up memory / OCR time.
_OCR_MAX_ZOOM = 600 / 72.0
# Absolute render-width cap (px). A digital-native page (e.g. a 1500pt broadsheet)
# rendered at the DPI floor balloons to ~4600px, which makes Tesseract crawl for
# no accuracy gain. Cap the width here — but NEVER below the page's own embedded
# scan resolution (capping a real scan would re-introduce the downsampling the
# native-res fix removed). So the effective ceiling is max(scan_px, _OCR_CAP_PX).
_OCR_CAP_PX = 2500.0

# Vision render DPI (smaller image keeps the request light).
_VISION_ZOOM = 96 / 72.0
# Clip crop quality.
_CLIP_RENDER_SCALE = 2.0
_CLIP_JPEG_QUALITY = 75
# A real article clip is at least this area (PDF pt^2). Smaller = caption strip
# / headline sliver -> reject rather than store a misleading snapshot.
_MIN_CLIP_AREA_PT = 8000.0

# Article-shape filter for geometry blocks (the layout fallback). A block must
# have at least this many body-scale lines walked beneath its headline, and be
# at least this many body-heights tall, to be treated as an article rather than
# an infographic cell or an orphan headline. Tuned so a headline (~2× body) plus
# a few body lines passes, while a single big number / two-word callout fails.
_MIN_BODY_LINES = 3
_MIN_BLOCK_H_BODYUNITS = 5.0

# Below this many OCR chars inside the crop, keep the Vision body instead (the
# OCR transcription is too sparse to be a useful grounded body).
_MIN_OCR_BODY_CHARS = 40
# Mean OCR per-line confidence below this flags the article for human review
# (garbled transcription). Tesseract scores clean newsprint ~0.80–0.95 and
# garbled text ~0.4–0.6, so 0.55 separates trustworthy bodies from suspect ones.
_CONF_REVIEW = 0.55

# Jump references and continuation markers that clutter the OCR body.
_JUMP_RE = re.compile(
    r"(?:PAGE\s*\d+|>>\s*\d+|CONTINUED|CONTD\.?|SEE\s+PAGE\s*\d*)", re.I
)
_WORD_RE = re.compile(r"[A-Za-z0-9ऀ-ൿ]+")  # Latin + Indic


def _toks(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text) if len(w) >= 3}


def _token_overlap(a: str, b: str) -> float:
    """Fraction of `a`'s content tokens that also appear in `b` (0–1).

    Used as a FREE confidence signal: how much of the Vision body is backed by
    the grounded OCR body. Low overlap → the crop/segmentation is suspect.
    """
    ta, tb = _toks(a), _toks(b)
    if not ta:
        return 0.0
    return len(ta & tb) / len(ta)


# ── OCR body cleanup (Vision-corroborated, so it can never corrupt) ───────────
# Principle: the Vision text is clean structure; use it to confirm every OCR
# repair. A fix only fires when Vision independently backs it, so genuine
# numbers and proper nouns are never mangled.

_STOP = {
    "is", "of", "in", "to", "a", "an", "the", "and", "on", "at", "for", "as",
    "by", "its",
}
# ₹ look-alike glyphs ($, %, ₨) directly before a lakh/crore/cr amount — a
# misread ₹ in Indian newsprint (which never quotes "$ … lakh/crore"). Genuine
# USD ("$64.6 billion") has no lakh/crore suffix so is untouched.
_RUPEE_LOOKALIKE = re.compile(r"[\$%₨](?=\s*[\d.,]+\s*(?:lakh|crore|cr)\b)", re.I)
# A number before lakh/crore/cr whose leading digit may be a merged ₹ glyph
# ("23,050 crore" ← "₹3,050 crore"). Only corrected when Vision corroborates.
_MERGED_RUPEE = re.compile(r"(?<![\d.])(\d)([\d,]*\d)(?=\s*(?:lakh|crore|cr)\b)", re.I)
_RUPEE_AMT = re.compile(r"(?:₹|Rs\.?)\s*([\d,]+(?:\.\d+)?)")

_wordseg_state: dict[str, object] = {"loaded": False, "mod": None, "uni": None}


def _load_wordseg() -> None:
    if _wordseg_state["loaded"]:
        return
    _wordseg_state["loaded"] = True
    try:
        import wordsegment  # type: ignore[import]

        wordsegment.load()
        _wordseg_state["mod"] = wordsegment
        _wordseg_state["uni"] = wordsegment.UNIGRAMS
    except Exception as exc:  # noqa: BLE001
        logger.info("wordsegment unavailable; merged-word split disabled: %s", exc)


def _rupee_amounts(vision_text: str) -> set[str]:
    """Comma-stripped numbers Vision printed right after a ₹/Rs marker."""
    return {m.group(1).replace(",", "") for m in _RUPEE_AMT.finditer(vision_text)}


def _fix_rupee(text: str, amounts: set[str]) -> str:
    text = _RUPEE_LOOKALIKE.sub("₹", text)
    if amounts:
        def repl(m: "re.Match[str]") -> str:
            lead, rest = m.group(1), m.group(2)
            if (lead + rest).replace(",", "") in amounts:
                return m.group(0)                  # the whole number is genuine
            if rest.replace(",", "") in amounts:   # leading digit is a merged ₹
                return "₹" + rest
            return m.group(0)
        text = _MERGED_RUPEE.sub(repl, text)
    return text


def _recase(raw: str, parts: list[str]) -> str:
    if raw.isupper():
        return " ".join(p.upper() for p in parts)
    if raw[:1].isupper():
        return " ".join(p.capitalize() for p in parts)
    return " ".join(parts)


def _split_merged(token: str, vocab: set[str]) -> str:
    """Split an OCR word-merge ("digitalassistant", "KIAINDIAIS").

    Two safe paths:
      • Vision-corroborated: every part is a stopword / in the article's Vision
        vocabulary / a dictionary word, AND at least one part (≥4 chars) is in
        the Vision vocabulary. This lets "KIAINDIAIS"→"KIA INDIA IS" fire (Vision
        wrote "Kia India is…") while "DELHI"/"MUMBAI" never split (Vision wrote
        them whole, and they are < 7 chars anyway).
      • Pure-dictionary: a lowercase run ≥9 chars that segments entirely into
        dictionary words — for merges Vision didn't happen to mention.
    Casing is preserved.
    """
    mod, uni = _wordseg_state["mod"], _wordseg_state["uni"]
    low = token.lower()
    if mod is None or not low.isalpha() or len(low) < 7 or low in uni:  # type: ignore[operator]
        return token
    parts = mod.segment(low)  # type: ignore[attr-defined]
    if len(parts) < 2:
        return token
    corroborated = (
        all(p in _STOP or p in vocab or (len(p) >= 3 and p in uni) for p in parts)
        and any(len(p) >= 4 and p in vocab for p in parts)
    )
    dict_only = (
        token == low and len(low) >= 9
        and all(len(p) >= 3 and p in uni for p in parts)
    )
    if corroborated or dict_only:
        return _recase(token, parts)
    return token


def _clean_ocr_body(text: str, vision_text: str = "") -> str:
    """Repair misread ₹ glyphs and OCR word-merges, corroborated by Vision."""
    _load_wordseg()
    # Strip a leading bullet glyph (•/◆ misread as ®/@/©/O/* by OCR) that opens
    # many sub-headline lines. Only at the very start, so a mid-text ™/® is safe.
    text = re.sub(r"^[\s®@©•◆○*·∙▪◦]+", "", text)
    text = _fix_rupee(text, _rupee_amounts(vision_text))
    vocab = _toks(vision_text)
    return " ".join(_split_merged(w, vocab) for w in text.split())

# Geometry/layout fallback for articles whose headline AND body both fail to
# match the OCR lines. It is an unverifiable guess (it picks a block by reading
# order, not by content) and has produced confidently-wrong crops, so it is off.
# Text- and body-anchored crops are content-verifiable; layout is not.
_ENABLE_LAYOUT_FALLBACK = False


# ── geometry helpers ──────────────────────────────────────────────────────────

def _ocr_zoom_for_page(doc, page, page_w_pt: float) -> float:
    """Pixels-per-point to render this page for OCR.

    Uses the native resolution of the page's largest embedded image when that
    exceeds the `_OCR_DPI` floor, so a high-res scan placed in a small page box
    is OCR'd at full detail rather than downsampled. Falls back to the floor for
    digital-native pages (no large raster) and clamps to `_OCR_MAX_ZOOM`.
    """
    native_zoom = 0.0
    native_px = 0
    try:
        if page_w_pt > 0:
            for img in page.get_images(full=True):
                info = doc.extract_image(img[0])
                native_px = max(native_px, int(info.get("width", 0)))
            if native_px > 0:
                native_zoom = native_px / page_w_pt
    except Exception as exc:  # noqa: BLE001
        logger.debug("native zoom probe failed: %s", exc)
    zoom = max(_OCR_ZOOM, min(native_zoom, _OCR_MAX_ZOOM))
    if page_w_pt > 0:
        # Cap the render width — but never below the embedded scan's own pixels,
        # so a genuine high-res scan keeps full detail while a digital-native
        # page stops ballooning past the cap.
        cap_px = max(float(native_px), _OCR_CAP_PX)
        if page_w_pt * zoom > cap_px:
            zoom = cap_px / page_w_pt
    return zoom


def _ocr_body_in_box(
    lines: list[OCRLine],
    box_px: list[float],
    headline: str = "",
    body_h: float = 0.0,
    vision_text: str = "",
) -> tuple[str, float]:
    """Join the OCR text inside box_px, in reading order, lightly cleaned.

    The crop region's own OCR transcription IS the article body — exactly what is
    printed on the page — so it cannot hallucinate the way the Vision retelling
    does. Newspaper bodies flow in narrow columns, so lines are grouped into
    columns (by x-start) and read left-column top-to-bottom, then the next column.

    Cleanup (safe, content-preserving):
      • drop a leading line that just repeats the headline (stored separately),
      • strip jump-refs / continuation markers ("PAGE 4", ">> 3", "Contd"),
      • cut at a clearly headline-scale line after the body has begun — that is
        the next article bleeding into a crop whose box spans two stories.
    """
    x0, y0, x1, y1 = box_px
    inside = [
        l for l in lines
        if x0 - 2.0 <= l.xc <= x1 + 2.0
        and y0 - 2.0 <= (l.y0 + l.y1) / 2.0 <= y1 + 2.0
        and (l.text or "").strip()
    ]
    if not inside:
        return "", 0.0
    # Mean OCR confidence over the crop's lines — a language-agnostic measure of
    # transcription quality (replaces the Vision↔OCR token overlap, which only
    # worked for English: in Indic, Vision paraphrases and OCR garbles, so the
    # overlap is near-zero even on good extractions and flagged everything).
    mean_conf = sum(l.conf for l in inside) / len(inside)
    # Column gutters: x-starts separated by more than a quarter of the box width
    # mark a new column.
    gap = max((x1 - x0) * 0.25, 30.0)
    inside.sort(key=lambda l: l.x0)
    col_edges: list[float] = [inside[0].x0]
    for l in inside[1:]:
        if l.x0 - col_edges[-1] > gap:
            col_edges.append(l.x0)

    def col_of(l: OCRLine) -> int:
        return min(range(len(col_edges)), key=lambda i: abs(l.x0 - col_edges[i]))

    inside.sort(key=lambda l: (col_of(l), l.y0))

    head_toks = _toks(headline)
    kept: list[str] = []
    body_started = False
    for l in inside:
        # Next-article headline bleeding into a two-story crop → stop here.
        if body_started and body_h > 0 and l.h >= body_h * 1.6 and len(l.text) >= 12:
            break
        text = _JUMP_RE.sub("", l.text).strip()
        if not text:
            continue
        lt = _toks(text)
        # Drop leading headline echo (before any body line has been seen).
        if not body_started and head_toks and lt and len(lt & head_toks) / len(lt) >= 0.6:
            continue
        kept.append(text)
        if body_h <= 0 or l.h <= body_h * 1.25:
            body_started = True
    # Corroborate cleanup against the headline + Vision body for this article.
    body = _clean_ocr_body(" ".join(kept), f"{headline} {vision_text}")
    return body, mean_conf


def _area(b: list[float]) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _iou(a: list[float], b: list[float]) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    ua = _area(a) + _area(b) - inter
    return inter / ua if ua > 0 else 0.0


def _contains(outer: list[float], inner: list[float]) -> bool:
    ia = _area(inner)
    if ia <= 0:
        return False
    ix0, iy0 = max(outer[0], inner[0]), max(outer[1], inner[1])
    ix1, iy1 = min(outer[2], inner[2]), min(outer[3], inner[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    return inter / ia >= 0.8


def _anchor_clip_box(
    article: dict, lines: list[OCRLine], ocr_w: float, ocr_h: float
) -> tuple[list[float], str] | None:
    """Locate a tight clip box from headline, subheadline, or body text.

    Returns (bbox_pixels, source) where source is "text" (headline/sub
    matched) or "body" (body-text column probe). Returns None when nothing
    could be matched.
    """
    for anchor in (article.get("headline", ""), article.get("subheadline", "")):
        if anchor and len(anchor) >= 6:
            box = locate_clip_box(anchor, lines, ocr_w, ocr_h)
            if box is not None:
                return box, "text"
    body = article.get("body", "")
    if body and len(body) >= 40:
        box = locate_clip_box_by_body(body, lines, ocr_w, ocr_h)
        if box is not None:
            return box, "body"
    return None


def _blocks_from_lines(
    lines: list[OCRLine], page_w_px: float
) -> list[list[float]]:
    """Derive article-region boxes from OCR line geometry (in OCR pixels).

    PP-Structure's layout model is trained on academic papers and collapses on
    dense newspaper pages (it returned ~1 region for a full broadsheet). But the
    OCR line boxes themselves carry the layout: a markedly larger-than-body line
    is a headline, and the body flows down its column beneath it. So we treat
    each big-font line as an article start and walk its column downward — the
    same idea as the text anchor, minus the text match, so it localises articles
    whose script OCRs to garbage. Language-agnostic; geometry only.
    """
    if not lines:
        return []
    heights = sorted(l.h for l in lines if l.h > 0)
    if not heights:
        return []
    body_h = heights[len(heights) // 4]  # 25th pct ≈ body type height
    # Headline-scale lines, but exclude logo/masthead-scale type (huge fonts are
    # nameplates and section banners, not article headlines).
    big = [
        l for l in lines
        if body_h * 1.6 <= l.h <= body_h * 6.0
        and l.x1 > l.x0
        and (l.x1 - l.x0) <= page_w_px * 0.55  # not a full-width banner line
    ]
    if not big:
        return []
    col_w = max(page_w_px / 7.0, 1.0)
    big.sort(key=lambda l: (int(l.x0 / col_w), l.y0))

    blocks: list[list[float]] = []
    for hl in big:
        x0, y0, x1, y1 = hl.x0, hl.y0, hl.x1, hl.y1
        band = sorted(
            (
                l for l in lines
                if l is not hl
                and hl.x0 <= (l.x0 + l.x1) / 2.0 <= hl.x1
                and l.y0 >= hl.y1 - body_h * 0.3
            ),
            key=lambda l: l.y0,
        )
        prev = hl.y1
        started = False
        body_lines = 0  # body-scale lines walked beneath the headline
        for l in band:
            if l.y0 - prev > body_h * 2.4:  # whitespace / section break
                break
            if l.h >= body_h * 1.6 and started:  # next article headline
                break
            if l.h <= body_h * 1.25:
                started = True
                body_lines += 1
            x0, y0, x1, y1 = min(x0, l.x0), min(y0, l.y0), max(x1, l.x1), max(y1, l.y1)
            prev = l.y1
        # Drop full-width blocks (mastheads, banner ads) — articles are columnar.
        if (x1 - x0) > page_w_px * 0.6:
            continue
        # ARTICLE-SHAPE FILTER. A geometry block only earns a crop if it looks
        # like a real article: a headline with body text flowing beneath it.
        # Without this, an infographic cell (one big number, a couple of words)
        # or an orphan headline (no body walked) becomes a confidently-wrong
        # crop — e.g. the "₹22,000-cr" CASE FILE cell mis-anchoring the Bombay
        # HC story onto its own sidebar. We require:
        #   • body actually started (≥ _MIN_BODY_LINES body-scale lines), and
        #   • the block is tall enough to hold a headline + body
        #     (≥ _MIN_BLOCK_H_BODYUNITS × body height).
        # A block that fails is dropped, leaving its article honestly
        # unanchored rather than cropped onto the wrong region.
        block_h = y1 - y0
        if body_lines < _MIN_BODY_LINES or block_h < body_h * _MIN_BLOCK_H_BODYUNITS:
            continue
        blocks.append([x0, y0, x1, y1])
    return blocks


def _reading_key(box: list[float], col_w: float) -> tuple[int, float]:
    """Reading-order sort key: (column index, vertical position)."""
    return (int(box[0] / col_w) if col_w > 0 else 0, box[1])


def _assign_layout_boxes(
    items: list[dict], layout_boxes: list[list[float]], page_w_pt: float
) -> None:
    """Place still-unanchored articles into geometry blocks, in reading order,
    constrained by the positions of the text-anchored articles around them.

    The previous version blind-zipped unanchored articles to blocks in list
    order, which mis-paired e.g. the Bombay HC story with an infographic block.
    Instead we use the text-anchored articles as spatial FIXED POINTS: `items`
    is in Vision reading order, so an unanchored article sitting between two
    text-anchored neighbours must occupy a block whose reading-order position
    also falls between those neighbours' boxes. We walk the articles in order
    and consume candidate blocks monotonically, never handing an article a block
    that lies before its last anchored neighbour. A block that would violate the
    ordering (or runs out) leaves the article honestly unanchored rather than
    cropped onto the wrong region.

    Blocks here are already article-shaped (see `_blocks_from_lines`), so the
    only remaining risk is *which* article a block belongs to — that is what the
    neighbour constraint addresses.
    """
    if not layout_boxes:
        return
    anchored_boxes = [it["bounding_box"] for it in items if it["clip_anchored"]]
    col_w = max(page_w_pt / 7.0, 1.0)
    avail = sorted(
        (
            lb for lb in layout_boxes
            if _area(lb) >= _MIN_CLIP_AREA_PT
            and max((_iou(lb, ab) for ab in anchored_boxes), default=0.0) < 0.3
        ),
        key=lambda b: _reading_key(b, col_w),
    )
    if not avail:
        return

    # Walk articles in Vision reading order. `lo` is the reading-order position
    # of the most recent text-anchored article — the lower bound for any block
    # we may assign to a subsequent unanchored article.
    lo: tuple[int, float] = (-1, -1.0)
    bi = 0  # pointer into the reading-order-sorted candidate blocks
    for it in items:
        if it["clip_anchored"]:
            lo = max(lo, _reading_key(it["bounding_box"], col_w))
            continue
        # Advance past any candidate block that sits before our lower bound
        # (it belongs to an earlier article's region, not this one).
        while bi < len(avail) and _reading_key(avail[bi], col_w) < lo:
            bi += 1
        if bi >= len(avail):
            break  # no candidate blocks left in reading order — leave unanchored
        lb = avail[bi]
        bi += 1
        it["bounding_box"] = lb
        it["clip_anchored"] = True
        it["clip_source"] = "layout"
        lo = max(lo, _reading_key(lb, col_w))


def _unanchor(it: dict, page_w: float, page_h: float) -> None:
    it["bounding_box"] = [0.0, 0.0, page_w, page_h]
    it["clip_anchored"] = False
    it["clip_source"] = "none"


def _apply_anchor_guards(items: list[dict], page_w: float, page_h: float) -> None:
    """Reject sliver crops and de-duplicate nested / overlapping boxes."""
    page_area = page_w * page_h
    for it in items:
        if not it["clip_anchored"]:
            continue
        box_area = _area(it["bounding_box"])
        if box_area < _MIN_CLIP_AREA_PT:
            _unanchor(it, page_w, page_h)
            continue
        # Layout-assigned boxes need a stricter page-percentage floor: a real
        # article occupies ≥1% of the page. Text-anchored boxes are trusted
        # (the headline matched) so they skip this check.
        if it["clip_source"] == "layout" and page_area > 0:
            bx = it["bounding_box"]
            bw, bh = bx[2] - bx[0], bx[3] - bx[1]
            if box_area / page_area < 0.01 or bw < 80.0 or bh < 80.0:
                _unanchor(it, page_w, page_h)

    anc = [it for it in items if it["clip_anchored"]]
    for a, b in itertools.combinations(anc, 2):
        if not (a["clip_anchored"] and b["clip_anchored"]):
            continue
        ba, bb = a["bounding_box"], b["bounding_box"]
        if _iou(ba, bb) > 0.5 or _contains(ba, bb) or _contains(bb, ba):
            # Prefer text-anchored over layout-assigned; among equals keep
            # the larger box.
            a_prio = 0 if a["clip_source"] == "text" else 1
            b_prio = 0 if b["clip_source"] == "text" else 1
            if a_prio != b_prio:
                _unanchor(b if b_prio > a_prio else a, page_w, page_h)
            else:
                _unanchor(b if _area(bb) <= _area(ba) else a, page_w, page_h)


def _crop_clip_b64(page, bbox_pts) -> str:
    """Render a PDF-points rectangle to a base64 JPEG."""
    import fitz  # PyMuPDF

    rect = fitz.Rect(*bbox_pts)
    pix = page.get_pixmap(
        matrix=fitz.Matrix(_CLIP_RENDER_SCALE, _CLIP_RENDER_SCALE), clip=rect
    )
    from PIL import Image

    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=_CLIP_JPEG_QUALITY)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


_TEXT_LAYER_MIN_CHARS = 800  # a page with this much embedded text is a digital PDF


def _lines_from_text_layer(page, zoom: float) -> list[OCRLine]:
    """Build OCR-equivalent lines from a digital PDF's embedded text layer, in
    the same pixel space as the OCR path (PDF points x ocr_zoom). Exact text and
    positions — no OCR error — so headline/body anchoring matches near-100%.
    """
    out: list[OCRLine] = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            txt = "".join(s.get("text", "") for s in line.get("spans", [])).strip()
            if not txt:
                continue
            x0, y0, x1, y1 = line["bbox"]
            out.append(
                OCRLine(text=txt, conf=1.0, x0=x0 * zoom, y0=y0 * zoom,
                        x1=x1 * zoom, y1=y1 * zoom)
            )
    return out


def _render_and_ocr(pdf_path: str, page_idx: int, language: str) -> dict:
    """CPU phase (runs in a worker thread): render the page, OCR it, prep the
    Vision image. Opens its own fitz.Document — fitz objects are not safe to
    share across threads, so each task gets an independent handle.
    """
    import fitz  # PyMuPDF
    import numpy as np
    from PIL import Image

    doc = fitz.open(pdf_path)
    try:
        page = doc[page_idx]
        page_w_pt, page_h_pt = page.rect.width, page.rect.height

        # Render at the embedded scan's native resolution (or DPI floor) so a
        # high-res Indic scan is never downsampled before OCR.
        ocr_zoom = _ocr_zoom_for_page(doc, page, page_w_pt)
        opix = page.get_pixmap(matrix=fitz.Matrix(ocr_zoom, ocr_zoom), colorspace=fitz.csRGB)
        ocr_w, ocr_h = float(opix.width), float(opix.height)

        # Prefer the embedded text layer when the page is a DIGITAL PDF (e.g. The
        # Hindu: ~11k chars/page with exact glyph positions). OCR of the rendered
        # scan was discarding those pages (~97% unanchored) by garbling the text
        # the anchor matches on; the text layer gives perfect text + boxes so
        # headline anchoring lands. Scanned papers (little/no text layer) keep the
        # OCR path unchanged.
        if len(page.get_text("text").strip()) >= _TEXT_LAYER_MIN_CHARS:
            lines = _lines_from_text_layer(page, ocr_zoom)
        else:
            oimg = np.frombuffer(opix.samples, dtype=np.uint8).reshape(
                opix.height, opix.width, 3
            )
            lines = [
                OCRLine(text=t, conf=c, x0=x0, y0=y0, x1=x1, y1=y1)
                for (t, c, x0, y0, x1, y1) in ocr_lines_best(oimg, lang=language)
            ]
        _hs = sorted(l.h for l in lines if l.h > 0)
        body_h_px = _hs[len(_hs) // 4] if _hs else 0.0
        block_boxes = [
            [v / ocr_zoom for v in b] for b in _blocks_from_lines(lines, ocr_w)
        ]

        vpix = page.get_pixmap(matrix=fitz.Matrix(_VISION_ZOOM, _VISION_ZOOM))
        vimg = Image.frombytes("RGB", [vpix.width, vpix.height], vpix.samples)
        vbuf = io.BytesIO()
        vimg.save(vbuf, format="JPEG", quality=70)
        vision_b64 = base64.b64encode(vbuf.getvalue()).decode("utf-8")

        return {
            "lines": lines, "block_boxes": block_boxes, "vision_b64": vision_b64,
            "page_w_pt": page_w_pt, "page_h_pt": page_h_pt, "ocr_zoom": ocr_zoom,
            "ocr_w": ocr_w, "ocr_h": ocr_h, "body_h_px": body_h_px,
        }
    finally:
        doc.close()


def _anchor_and_crop(
    pdf_path: str, page_idx: int, od: dict, articles: list[dict],
    language: str, with_clip_images: bool,
) -> list[dict]:
    """CPU phase (runs in a worker thread): anchor each Vision article to a clip
    box, apply guards, then crop + extract the grounded OCR body + confidence.
    """
    import fitz  # PyMuPDF

    lines = od["lines"]
    ocr_zoom, body_h_px = od["ocr_zoom"], od["body_h_px"]
    ocr_w, ocr_h = od["ocr_w"], od["ocr_h"]
    page_w_pt, page_h_pt = od["page_w_pt"], od["page_h_pt"]

    page_items: list[dict] = []
    for a in articles:
        result = _anchor_clip_box(a, lines, ocr_w, ocr_h)
        if result is not None:
            box_px, source = result
            bbox_pts = [v / ocr_zoom for v in box_px]
            anchored = True
        else:
            bbox_pts = [0.0, 0.0, page_w_pt, page_h_pt]
            anchored, source = False, "none"
        page_items.append({
            "headline": a["headline"],
            "subheadline": a.get("subheadline", ""),
            "byline": a.get("byline", ""),
            "text": a["body"],
            "vision_text": a["body"],
            "text_source": "vision",
            "bounding_box": bbox_pts,
            "page_number": page_idx + 1,
            "section": a.get("section", ""),
            "detected_language": a.get("language") or language,
            "continuation_page": None,
            "clip_anchored": anchored,
            "clip_source": source,
            # Statutory/legal/IPO/auction notice rather than editorial news.
            "is_notice": is_notice(a["headline"], a.get("body", "")),
            "is_duplicate": False,
            "duplicate_of": None,
        })

    if _ENABLE_LAYOUT_FALLBACK:
        _assign_layout_boxes(page_items, od["block_boxes"], page_w_pt)
    _apply_anchor_guards(page_items, page_w_pt, page_h_pt)

    doc = fitz.open(pdf_path)
    try:
        page = doc[page_idx]
        for it in page_items:
            clip_b64 = ""
            if it["clip_anchored"]:
                box_px = [v * ocr_zoom for v in it["bounding_box"]]
                ocr_body, ocr_conf = _ocr_body_in_box(
                    lines, box_px, it["headline"], body_h_px, it["vision_text"]
                )
                if len(ocr_body) >= _MIN_OCR_BODY_CHARS:
                    it["text"] = ocr_body
                    it["text_source"] = "ocr"
                it["extraction_confidence"] = round(ocr_conf, 2)
                it["needs_review"] = ocr_conf < _CONF_REVIEW
                if with_clip_images:
                    try:
                        clip_b64 = _crop_clip_b64(page, it["bounding_box"])
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("hybrid: clip crop failed: %s", exc)
            else:
                it["extraction_confidence"] = None
                it["needs_review"] = False
            it["clipping_image_b64"] = clip_b64
    finally:
        doc.close()
    return page_items


async def extract_articles_hybrid(
    pdf_path: str,
    paper_id: str | None = None,
    language: str = "en",
    max_pages: int = 24,
    with_clip_images: bool = True,
) -> list[dict]:
    """Vision-segmented articles with text- or layout-anchored clip boxes."""
    try:
        import fitz  # PyMuPDF
        import numpy as np
    except ImportError as exc:  # noqa: BLE001
        logger.warning("hybrid pipeline missing deps: %s", exc)
        return []

    try:
        from backend.nlp.groq_client import groq_manager
    except Exception as exc:  # noqa: BLE001
        logger.warning("hybrid pipeline: Groq unavailable: %s", exc)
        return []

    doc = fitz.open(pdf_path)
    n = min(len(doc), max_pages)
    doc.close()

    # Process pages concurrently: the heavy CPU phases (render + OCR, then
    # anchor + crop) run in worker threads — Tesseract is a subprocess so it
    # parallelises across cores — while the Vision call awaits between them. A
    # semaphore caps in-flight pages to bound memory and Vision-API pressure.
    sem = asyncio.Semaphore(_PAGE_CONCURRENCY)

    async def _process_page(page_idx: int) -> list[dict]:
        async with sem:
            od = await asyncio.to_thread(_render_and_ocr, pdf_path, page_idx, language)
            articles = await segment_page(od["vision_b64"], groq_manager)
            logger.info(
                "hybrid page %d/%d: %d OCR lines, %d vision articles, %d blocks",
                page_idx + 1, n, len(od["lines"]), len(articles), len(od["block_boxes"]),
            )
            return await asyncio.to_thread(
                _anchor_and_crop, pdf_path, page_idx, od, articles,
                language, with_clip_images,
            )

    pages = await asyncio.gather(*[_process_page(i) for i in range(n)])
    out = [it for page_items in pages for it in page_items]
    # Cross-page de-duplication (front-page teaser ↔ full inside-page story).
    mark_duplicates(out)
    n_notice = sum(1 for it in out if it.get("is_notice"))
    n_dupe = sum(1 for it in out if it.get("is_duplicate"))
    logger.info(
        "hybrid: %d articles from %s (%d notices, %d duplicates)",
        len(out), pdf_path, n_notice, n_dupe,
    )
    return out
