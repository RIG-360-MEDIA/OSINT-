"""
Colour-based body/non-body line filtering for newspaper crops.

Newspaper body text is black ink on near-white newsprint (low colour
saturation). Infographics, charts, callout boxes, section kickers and
advertisements use colour (high saturation). Measuring the mean saturation of
each OCR line's pixel region lets us drop chart/ad/box text while keeping the
article body — deterministically, with no risk of dropping real content.
"""
from __future__ import annotations

import numpy as np


def _mean_saturation(img: np.ndarray, x0: float, y0: float, x1: float, y1: float) -> float:
    """Mean HSV-saturation of an RGB image region (0..1)."""
    h, w = img.shape[:2]
    a, b = max(0, int(y0)), min(h, int(y1))
    c, d = max(0, int(x0)), min(w, int(x1))
    if b <= a or d <= c:
        return 0.0
    reg = img[a:b, c:d].astype(np.float32)
    mx = reg.max(axis=2)
    mn = reg.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.clip(mx, 1.0, None), 0.0)
    return float(sat.mean())


def is_body_line(
    img: np.ndarray,
    box: tuple[float, float, float, float],
    threshold: float = 0.18,
) -> bool:
    """True if the line sits on a near-white (low-saturation) background."""
    return _mean_saturation(img, *box) < threshold


def filter_body_lines(
    img: np.ndarray,
    lines: list[tuple[str, float, float, float, float]],
    threshold: float = 0.18,
) -> list[tuple[str, float, float, float, float]]:
    """Keep only lines on a near-white background.

    Each line is (text, x0, y0, x1, y1) in image-pixel coordinates.
    """
    return [
        ln for ln in lines
        if is_body_line(img, (ln[1], ln[2], ln[3], ln[4]), threshold)
    ]
