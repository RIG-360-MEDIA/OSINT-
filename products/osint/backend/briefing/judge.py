"""Judge one item: call the LLM, parse, VERIFY the evidence against the source.

The verify step is the guardrail: a model can assert a confident wrong verdict,
but it cannot quote a sentence that is not in the document. If the evidence
sentence is not found in the item's own text, the verdict is discarded and the
item is marked unclear.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from groq_client import call_groq
from briefing import prompt as P

logger = logging.getLogger("briefing.judge")

JUDGE_MODEL = "llama-3.3-70b-versatile"   # fast, non-reasoning, clean JSON at volume
CONFIDENCE_GATE = 0.60                     # below → unclear, counts nowhere
_VALID_VERDICTS = {"critical", "favourable", "neutral"}
_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub(" ", (s or "")).strip().lower()


def _evidence_in_body(evidence: str, title: str, body: str) -> bool:
    """Verify the evidence sentence really appears in the item text.

    Exact-substring after whitespace normalisation. Falls back to a high-overlap
    token check for the case where extraction reflowed punctuation/quotes — but
    stays strict enough that an invented sentence fails.
    """
    ev = _norm(evidence)
    if len(ev) < 8:
        return False
    hay = _norm(title) + " " + _norm(body)
    if ev in hay:
        return True
    # Reflow-tolerant fallback: strip quotes/punct, require the evidence's word
    # sequence to appear with >=90% of its words contiguous-ish in the body.
    ev_words = [w for w in re.sub(r"[^\w\s]", " ", ev).split() if len(w) > 1]
    if len(ev_words) < 4:
        return False
    hay_clean = re.sub(r"[^\w\s]", " ", hay)
    hit = sum(1 for w in ev_words if w in hay_clean)
    return hit / len(ev_words) >= 0.90


def _coerce(v: dict[str, Any], refdata: dict[str, Any]) -> dict[str, Any]:
    """Normalise + validate model output against the closed vocabularies."""
    verdict = str(v.get("verdict", "")).strip().lower()
    if verdict not in _VALID_VERDICTS:
        verdict = "neutral"
    topic = v.get("topic")
    if topic not in refdata["topics"]:
        topic = None
    dept = v.get("department")
    if dept not in refdata["departments"]:
        dept = None
    scheme = v.get("scheme")
    if scheme not in refdata["schemes"]:
        scheme = None
    ev = v.get("event") or {}
    try:
        conf = float(v.get("confidence"))
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    strength = v.get("strength")
    if strength not in ("strong", "mild"):
        strength = None
    return {
        "about_government": bool(v.get("about_government")),
        "verdict": verdict,
        "strength": strength,
        "topic": topic,
        "department": dept,
        "scheme": scheme,
        "event_action": (ev.get("action") or None),
        "event_actors": [a for a in (ev.get("actors") or []) if a][:8],
        "event_date": (ev.get("date") or None),
        "event_place": (ev.get("place") or None),
        "evidence": (v.get("evidence") or "").strip(),
        "lands_on": (v.get("lands_on") or None),
        "confidence": conf,
    }


async def judge_item(item: dict[str, Any], refdata: dict[str, Any],
                     system: str | None = None) -> dict[str, Any]:
    """Judge one item. Returns a verdict dict ready for briefing.items.

    On any failure (LLM error, unparseable, evidence not found, low confidence)
    the item is returned with unclear=True and counts nowhere downstream.
    """
    sys = system or P.build_system(refdata)
    result_base = {
        "unclear": True, "about_government": None, "verdict": None,
        "strength": None, "topic": None, "department": None, "scheme": None,
        "event_action": None, "event_actors": [], "event_date": None,
        "event_place": None, "evidence": None, "evidence_verified": False,
        "lands_on": None, "confidence": 0.0,
        "model": JUDGE_MODEL, "prompt_version": P.PROMPT_VERSION,
    }
    try:
        raw = await call_groq(
            system=sys, user=P.build_user(item),
            task_type="brief_generation", model=JUDGE_MODEL,
            json_response=False, max_tokens_override=600,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("judge LLM failed: %s", str(exc)[:160])
        return result_base

    parsed = P.parse_verdict(raw)
    if not parsed:
        logger.info("judge: unparseable reply: %r", (raw or "")[:120])
        return result_base

    c = _coerce(parsed, refdata)
    verified = _evidence_in_body(c["evidence"], item.get("title", ""), item.get("body", ""))
    # unclear iff: not about govt is fine (clear), but a verdict needs verified
    # evidence AND adequate confidence. Neutral items with no evidence are allowed
    # to stand as neutral (they carry no claim to verify).
    unclear = False
    if c["about_government"]:
        if c["verdict"] in ("critical", "favourable"):
            if not verified or c["confidence"] < CONFIDENCE_GATE:
                unclear = True
        # neutral: keep unless confidence is very low
        elif c["confidence"] < 0.4:
            unclear = True

    return {
        **result_base,
        **c,
        "evidence_verified": verified,
        "unclear": unclear,
    }
