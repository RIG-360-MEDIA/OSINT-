"""
Article assembly from PP-Structure OCR regions.

PP-Structure classifies each page region as title / text / figure / table.
We use that classification directly instead of inferring it from font size:

  title  → start a new article candidate
  text   → append as body to the current article
  figure → skip (photos; text may re-appear as figure_caption below)
  table  → append as body (committee lists, results tables, etc.)

Reading order
-------------
PP-Structure returns regions in detection order, which is roughly spatial but
not guaranteed to follow left-column-first reading order for multi-column pages.
We sort by a "column stripe" key: (x0 // col_w, y0). Using page_width / 7 as
the column width estimate works for both broadsheet (7-col) and tabloid (4-5 col)
papers — the key concern is left-before-right, which this preserves.

Headline fallback
-----------------
If PP-Structure's layout model misclassifies a large headline as "text"
(common when the headline font differs from its training distribution), we
catch it with an estimated-font-size check: a text region whose bbox height
implies ≥ 14 pt is promoted to headline if no article is open yet, or if
there is a significant vertical gap since the last text.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from .ocr import OCRRegion

logger = logging.getLogger(__name__)

_CONT_RE = re.compile(
    r"(?i)(?:continued?\s+on\s+(?:page|pg\.?)\s*(\d+)"
    r"|→\s*p(?:age|g\.?)\s*(\d+)"
    r"|\(turn\s+to\s+p(?:age|g\.?)\s*(\d+)\))"
)

# A text region this tall (pts) is treated as a headline even without type='title'
_HEADLINE_FONT_PT = 14.0
# Minimum body length (chars) to keep an article
_MIN_BODY_CHARS = 60


@dataclass
class _Art:
    headline: str
    body_parts: list[str] = field(default_factory=list)
    page_number: int = 1
    bbox: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    continuation_page: int | None = None

    @property
    def body(self) -> str:
        return " ".join(self.body_parts).strip()

    def to_dict(self) -> dict:
        return {
            "headline": self.headline,
            "text": self.body,
            "bounding_box": self.bbox,
            "page_number": self.page_number,
            "section": "",
            "detected_language": "",
            "continuation_page": self.continuation_page,
        }


def assemble_articles(
    pages_regions: list[list[OCRRegion]],
    max_articles: int = 120,
) -> list[dict]:
    """
    Convert per-page PP-Structure regions into article dicts.

    Returns [{headline, text, bounding_box, page_number, section,
              detected_language, continuation_page}]
    """
    out: list[dict] = []
    for page_regions in pages_regions:
        for art in _assemble_page(page_regions):
            if art.headline and len(art.body) >= _MIN_BODY_CHARS:
                out.append(art.to_dict())
                if len(out) >= max_articles:
                    return out
    return out


def _assemble_page(regions: list[OCRRegion]) -> list[_Art]:
    if not regions:
        return []

    pw = regions[0].page_width or 1.0
    col_w = pw / 7.0  # reading-order stripe width

    # Sort: left column first (x0 stripe), then top-to-bottom within column
    ordered = sorted(regions, key=lambda r: (int(r.x0 / col_w), r.y0))

    arts: list[_Art] = []
    cur: _Art | None = None

    for r in ordered:
        # Skip empty regions
        if not r.text and r.type not in ("figure",):
            continue

        is_title = (
            r.type == "title"
            or r.type == "figure_caption"  # captions near images sometimes headline
            or (r.type == "text" and r.estimated_font_pt >= _HEADLINE_FONT_PT and not cur)
        )

        if is_title and r.text:
            if cur and cur.body:
                arts.append(cur)
            cur = _Art(
                headline=r.text[:300],
                page_number=r.page_number,
                bbox=[r.x0, r.y0, r.x1, r.y1],
            )

        elif r.type in ("text", "table") and r.text:
            cont = _check_continuation(r.text)
            if cont:
                if cur:
                    cur.continuation_page = cont
            elif cur is not None:
                cur.body_parts.append(r.text)
                cur.bbox = _expand(cur.bbox, r)
            elif len(r.text) > 200:
                # Orphan body before any title → make it its own stub article
                cur = _Art(
                    headline=r.text[:80].rstrip() + "…",
                    body_parts=[r.text[80:]],
                    page_number=r.page_number,
                    bbox=[r.x0, r.y0, r.x1, r.y1],
                )

    if cur and cur.body:
        arts.append(cur)

    return arts


def _check_continuation(text: str) -> int | None:
    m = _CONT_RE.search(text)
    if not m:
        return None
    pg_str = next((g for g in m.groups() if g), None)
    try:
        return int(pg_str) if pg_str else None
    except ValueError:
        return None


def _expand(bbox: list[float], r: OCRRegion) -> list[float]:
    return [
        min(bbox[0], r.x0), min(bbox[1], r.y0),
        max(bbox[2], r.x1), max(bbox[3], r.y1),
    ]
