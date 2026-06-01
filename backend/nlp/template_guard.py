#!/usr/bin/env python3
"""
template_guard.py — deterministic false-merge guard for clustering job #7.

Mining (v1/v2/v3) proved false-merges concentrate in recurring SAME-SOURCE templates
(daily front-pages, horoscopes, per-stock tickers, per-match previews). The scorer
cannot learn this (too few negatives), so it is a HARD RULE applied BEFORE edge
creation. Language-agnostic by design — numeric DD-MM dates fire across scripts, so it
covers Indic templates with no Indic training data (handoff §3).

Rule (clustering-job-7-build-handoff-2026-06-02 §3):
  Block the edge IFF  same_source  AND  title_trgm >= TRGM_MIN  AND a differing instance-key:
    * different calendar DATE in the titles   (trusted form — v3: 30/33 = ~91% precision)  OR
    * different lead ENTITY  (valid ONLY combined with same-source + near-identical title;
      entity-key alone is ~14% — never used standalone)

`shared_numbers` is POSITIVE-ONLY elsewhere; numeric divergence is NEVER consulted here
and must never trigger a split (same-event coverage diverges numerically constantly —
proven in the v2 mine). This module takes no number input by construction.
"""
from __future__ import annotations

import re

TEMPLATE_GUARD_VERSION = "tg-v1-2026-06-02"
TRGM_MIN = 0.85

_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
# English month+day  OR  language-agnostic numeric DD-MM(-YYYY) / DD/MM (tolerates stray spaces).
_DATE_RE = re.compile(
    rf"(?:{_MONTHS})[a-z]*\.?\s*\d{{1,2}}"
    r"|\b\d{1,2}\s*[-/]\s*\d{1,2}(?:\s*[-/]\s*\d{2,4})?\b",
    re.I,
)


def title_dates(title: str) -> frozenset[str]:
    """Calendar dates present in a title, normalised (whitespace/dots stripped, lower)."""
    return frozenset(re.sub(r"[\s.]+", "", m).lower() for m in _DATE_RE.findall(title or ""))


def block_edge(*, same_source: bool, title_trgm: float, a_title: str, b_title: str,
               a_lead_entity: str | None = None, b_lead_entity: str | None = None,
               trgm_min: float = TRGM_MIN) -> tuple[bool, str]:
    """Decide whether to BLOCK an edge between two articles (template-instance guard).

    Returns (block, reason). block=True  -> do NOT create the edge (different instance of
    the same recurring template). block=False -> the guard does not apply; let the scorer
    decide. Numbers are intentionally NOT a parameter (positive-only signal lives elsewhere).
    """
    if not same_source:
        return False, "different source — not a template pair"
    if title_trgm < trgm_min:
        return False, f"titles not near-identical (trgm {title_trgm:.2f} < {trgm_min})"
    da, db = title_dates(a_title), title_dates(b_title)
    if da and db and da != db:
        return True, f"same-source template, different title date {sorted(da)} vs {sorted(db)}"
    if a_lead_entity and b_lead_entity and a_lead_entity.strip().lower() != b_lead_entity.strip().lower():
        return True, f"same-source template, different lead entity '{a_lead_entity}' vs '{b_lead_entity}'"
    return False, "same template, no differing instance-key — allow merge"
