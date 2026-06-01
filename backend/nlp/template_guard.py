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

TEMPLATE_GUARD_VERSION = "tg-v2-2026-06-02"  # v2: + subject-template entity-key
TRGM_MIN = 0.85
SUBJ_MIN = 0.85   # subject-template guard: near-identical primary_subject threshold

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
               subj_trgm: float | None = None,
               trgm_min: float = TRGM_MIN, subj_min: float = SUBJ_MIN) -> tuple[bool, str]:
    """Decide whether to BLOCK an edge between two articles (template-instance guard).

    Same-source only. Two template forms, each requires a differing instance-key:
      * TITLE-template (title_trgm >= trgm_min): different calendar DATE (trusted, ~91%)
        OR different lead ENTITY.
      * SUBJECT-template (subj_trgm >= subj_min): titles differ, but the primary_subject is
        template-similar ("Q4 Results", "Memorial Day store hours") AND the lead ENTITY
        differs (different company / store) -> different instance.
    Never on entity-difference alone (the same-source + similarity conjunction gates it);
    numbers are never consulted (positive-only signal lives elsewhere). block=False ->
    guard does not apply; let the scorer decide.
    """
    if not same_source:
        return False, "different source — not a template pair"
    diff_entity = bool(a_lead_entity and b_lead_entity
                       and a_lead_entity.strip().lower() != b_lead_entity.strip().lower())
    if title_trgm >= trgm_min:
        da, db = title_dates(a_title), title_dates(b_title)
        if da and db and da != db:
            return True, f"same-source title-template, different title date {sorted(da)} vs {sorted(db)}"
        if diff_entity:
            return True, f"same-source title-template, different lead entity '{a_lead_entity}' vs '{b_lead_entity}'"
    if subj_trgm is not None and subj_trgm >= subj_min and diff_entity:
        return True, (f"same-source subject-template (trgm_subj {subj_trgm:.2f}), "
                      f"different lead entity '{a_lead_entity}' vs '{b_lead_entity}'")
    return False, "no differing instance-key — allow merge"
