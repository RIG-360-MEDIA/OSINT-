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

import os
import re

TEMPLATE_GUARD_VERSION = "tg-v4-2026-06-02"  # v4: + cross-source template veto; same-source block_edge unchanged
TRGM_MIN = 0.85
SUBJ_MIN = float(os.environ.get("TG_SUBJ_MIN", "0.85"))  # subject-template threshold (env-tunable for the knee sweep)
T_STRUCT = float(os.environ.get("T_STRUCT", "0.75"))     # cross-source: structural (subject) near-identity threshold

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
               a_entities=None, b_entities=None,
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
    a_set = {e.strip().lower() for e in (a_entities or ([a_lead_entity] if a_lead_entity else [])) if e}
    b_set = {e.strip().lower() for e in (b_entities or ([b_lead_entity] if b_lead_entity else [])) if e}
    a_only, b_only = a_set - b_set, b_set - a_set
    diff_entity = bool(a_set and b_set and a_only and b_only)
    if title_trgm >= trgm_min:
        da, db = title_dates(a_title), title_dates(b_title)
        if da and db and da != db:
            return True, f"same-source title-template, different title date {sorted(da)} vs {sorted(db)}"
        if diff_entity:
            return True, f"same-source title-template, distinct entities {sorted(a_only)} vs {sorted(b_only)}"
    if subj_trgm is not None and subj_trgm >= subj_min and diff_entity:
        return True, (f"same-source subject-template (trgm_subj {subj_trgm:.2f}), "
                      f"distinct entities {sorted(a_only)} vs {sorted(b_only)}")
    return False, "no differing instance-key — allow merge"


def block_cross_source_template(*, subj_trgm, a_entities=None, b_entities=None,
                                shared_numbers: int = 0,
                                a_has_numbers: bool = False, b_has_numbers: bool = False,
                                shared_locations: int = 0,
                                t_struct: float = T_STRUCT) -> tuple[bool, str]:
    """Cross-source template veto (v2 #1, spec cross-source-template-guard §2a).

    Same SHAPE as block_edge's entity-key, but DROPS the same_source requirement and ADDS a
    numbers-divergence condition — which is what makes it safe across outlets: two outlets on
    the SAME event share numbers and/or a location anchor; two outlets on DIFFERENT template
    instances (NTPC-Q4 vs Zydus-Q4, Walmart-hours vs Costco-hours) share neither. Blocks IFF
    ALL hold:
      * subject structurally near-identical   (subj_trgm >= t_struct), AND
      * primary entities BOTH-SIDED DISTINCT   (different instance actor), AND
      * numbers DIVERGE: both sides carry figures but share NONE, AND
      * NO shared specific-location anchor      (real events share a place).

    Retention (§3): numbers-divergence ALONE never vetoes — the entity-divergence AND
    no-anchor conditions protect a real evolving event ("82->90 dead", same place/actor,
    diverging numbers). Returns (block, reason); block=False -> let the scorer decide.
    """
    if subj_trgm is None or subj_trgm < t_struct:
        return False, "subject not structurally near-identical — not a template pair"
    a_set = {e.strip().lower() for e in (a_entities or []) if e}
    b_set = {e.strip().lower() for e in (b_entities or []) if e}
    if not (a_set and b_set and (a_set - b_set) and (b_set - a_set)):
        return False, "entities not both-sided distinct (shared actor -> likely same event)"
    if not (a_has_numbers and b_has_numbers and (shared_numbers or 0) == 0):
        return False, "numbers not divergent (shared/absent figures -> not a template instance)"
    if (shared_locations or 0) > 0:
        return False, "shared location anchor -> likely same event, not a template"
    return True, (f"cross-source template: structural match + distinct entities "
                  f"{sorted(a_set - b_set)} vs {sorted(b_set - a_set)} + divergent numbers + no anchor")
