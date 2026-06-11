"""
Compute per-paper extraction-quality metrics from a hybrid-extractor summary.

Reads a summary.json produced by verify_hybrid_extraction.py and prints a
single-line-per-metric report covering the five quality fields plus a computed
mis-anchor check (anchored boxes that overlap heavily on the same page are
likely cross-article mis-anchors).

Usage:  python eval_extraction_metrics.py <summary.json> <label>
"""
from __future__ import annotations

import itertools
import json
import sys


def _iou(a: list[float], b: list[float]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    ua = (
        max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
        + max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
        - inter
    )
    return inter / ua if ua > 0 else 0.0


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/hybrid_out/summary.json"
    label = sys.argv[2] if len(sys.argv) > 2 else "paper"
    d = json.load(open(path, encoding="utf-8"))
    n = len(d) or 1
    anc = [x for x in d if x.get("anchored")]

    by_page: dict = {}
    for x in anc:
        if len(x.get("bbox") or []) == 4:
            by_page.setdefault(x.get("page"), []).append(x)
    overlaps = 0
    for items in by_page.values():
        for a, b in itertools.combinations(items, 2):
            if _iou(a["bbox"], b["bbox"]) > 0.5:
                overlaps += 1

    bl = [x.get("body_len", 0) for x in d]
    print(
        f"{label} | total {len(d)} | anchored {len(anc)} "
        f"| subhead {sum(1 for x in d if x.get('subheadline'))} "
        f"| byline {sum(1 for x in d if x.get('byline'))} "
        f"| multi_para {sum(1 for x in d if x.get('body_paras', 0) > 1)} "
        f"| img {sum(1 for x in d if x.get('img_kb', 0) > 2)}"
    )
    print(
        f"  body_len min/avg/max {min(bl)}/{round(sum(bl) / n)}/{max(bl)} "
        f"| empty_headline {sum(1 for x in d if not (x.get('headline') or '').strip())} "
        f"| mis_anchor_overlap_pairs {overlaps} "
        f"| tiny_crops(<8kb) {sum(1 for x in anc if 0 < x.get('img_kb', 0) < 8)} "
        f"| unanchored {sum(1 for x in d if not x.get('anchored'))}"
    )


if __name__ == "__main__":
    main()
