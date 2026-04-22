"""
Structured intelligence extraction for government documents.

Calls Groq once per doc with a 15-field JSON schema prompt.
Returns a validated GovtDocIntel pydantic model.
Computes a deterministic intrinsic_importance score (0-1) from the intel.
"""
from __future__ import annotations

import logging
from math import log10

from backend.nlp.groq_client import (
    GroqCallFailed,
    GroqQuotaExhausted,
    extract_json,
)
from backend.nlp.govt_intel_schema import GovtDocIntel

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You are a policy intelligence analyst extracting structured data from government documents.

Return ONLY a JSON object with these exact keys:
{
  "what_it_does":           string (1 sentence, verb-led),
  "who_it_affects":         array of strings (concrete groups: "farmers", "Adilabad district officials", "Telangana State PSUs"),
  "what_changes":           string or null (before X, after Y),
  "financial_magnitude_inr": integer or null (total rupees involved, NOT crores or lakhs),
  "effective_date":         "YYYY-MM-DD" or null,
  "deadline_dates":         array of "YYYY-MM-DD" strings,
  "geography_affected":     array of strings (states/districts/cities; if pan-India, use ["India"]),
  "sectors_affected":       array of strings (e.g. "irrigation", "education", "manufacturing"),
  "winners":                array of strings (specific groups who benefit),
  "losers":                 array of strings (specific groups who are harmed or restricted),
  "contradicts_prior":      boolean,
  "contradicts_what":       string or null,
  "precedent_setting":      boolean,
  "enforcement_strength":   "BINDING" | "ADVISORY" | "ASPIRATIONAL" | null,
  "document_nature":        one of: ORDER, NOTIFICATION, CIRCULAR, GAZETTE, POLICY, AMENDMENT, TENDER, JUDGMENT, AUDIT_REPORT, BUDGET, RTI_RESPONSE, COMMITTEE_REPORT, BILL, MINUTES, OTHER,
  "action_posture":         one of: NEW_POLICY, EXPANSION, RESTRICTION, REPEAL, EXEMPTION, PUNITIVE, REWARD, INVESTIGATION, TRANSPARENCY, ROUTINE_ADMIN, OTHER
}

Rules:
- If a field cannot be determined from the text, use null or empty array
- Convert all monetary amounts to rupees (e.g. "847 crore" -> 8470000000)
- Use canonical place names (Telangana not "TG"; Hyderabad not "HYD")
- Keep what_it_does under 25 words"""


async def extract_intel(text: str, title: str) -> GovtDocIntel:
    """Run Groq intel extraction on a govt-doc text. Returns GovtDocIntel.

    On failure (quota, parse error, validation), returns a minimal default
    GovtDocIntel with what_it_does=title so the pipeline doesn't break.
    """
    safe_title = (title or "").strip() or "Untitled document"
    user_msg = f"Title: {safe_title}\n\nDocument text:\n{(text or '')[:8000]}"
    try:
        raw = await extract_json(
            system=_SYSTEM_PROMPT,
            user=user_msg,
            task_type="profile_extraction",
        )
        return GovtDocIntel(**raw)
    except (GroqQuotaExhausted, GroqCallFailed) as exc:
        logger.warning("Groq intel extraction failed for %r: %s", safe_title[:60], exc)
        return GovtDocIntel(what_it_does=safe_title[:200])
    except Exception as exc:
        logger.warning("Intel JSON validation failed for %r: %s", safe_title[:60], exc)
        return GovtDocIntel(what_it_does=safe_title[:200])


# Document nature -> base importance weight (0-1)
_NATURE_WEIGHT: dict[str, float] = {
    "ORDER":            1.00,
    "JUDGMENT":         0.95,
    "POLICY":           0.90,
    "BUDGET":           0.90,
    "AUDIT_REPORT":     0.80,
    "BILL":             0.75,
    "AMENDMENT":        0.70,
    "GAZETTE":          0.65,
    "NOTIFICATION":     0.60,
    "TENDER":           0.55,
    "COMMITTEE_REPORT": 0.55,
    "CIRCULAR":         0.40,
    "MINUTES":          0.30,
    "RTI_RESPONSE":     0.25,
    "OTHER":            0.20,
}


def compute_intrinsic_importance(intel: GovtDocIntel) -> float:
    """Deterministic 0-1 score from nature, money, enforcement, precedent, geography.

    No LLM call - pure function. Same doc -> same score every time.
    """
    score = _NATURE_WEIGHT.get(intel.document_nature, 0.2)

    # Financial magnitude bump: log10-scaled.
    # ~1 cr (1e7) -> +0.025, ~100 cr (1e9) -> +0.075, ~10000 cr (1e11) -> +0.125
    if intel.financial_magnitude_inr and intel.financial_magnitude_inr > 0:
        magnitude_bump = min(
            0.20,
            max(0.0, (log10(intel.financial_magnitude_inr) - 6) * 0.025),
        )
        score = min(1.0, score + magnitude_bump)

    # Enforcement strength
    if intel.enforcement_strength == "BINDING":
        score = min(1.0, score + 0.05)
    elif intel.enforcement_strength == "ASPIRATIONAL":
        score = max(0.0, score - 0.05)

    # Precedent flag
    if intel.precedent_setting:
        score = min(1.0, score + 0.05)

    # Geography breadth: pan-India docs get a small bump (national scope)
    if "India" in intel.geography_affected:
        score = min(1.0, score + 0.03)

    # Routine admin penalty
    if intel.action_posture == "ROUTINE_ADMIN":
        score = max(0.0, score - 0.15)

    return round(score, 3)
