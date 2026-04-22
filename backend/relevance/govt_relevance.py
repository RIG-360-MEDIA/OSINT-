"""
Govt-doc per-user relevance scorer.

Two-stage hybrid (mirrors article scorer pattern but uses govt-doc inputs):
  Stage 1 - rules-based, ~5ms, computes score_stage1 from entity/geo/topic/intrinsic
  Stage 2 - Groq call (only if Stage 1 >= 0.25), produces urgency/why/suggested_action

Result cached in user_govt_doc_relevance. Returns cached row if doc.updated_at
predates cache.computed_at.

THIS FILE OWNS: backend/relevance/govt_relevance.py
DOES NOT TOUCH: backend/nlp/relevance_scorer.py (article scorer is sacred)
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text

from backend.nlp.groq_client import (
    GroqCallFailed,
    GroqQuotaExhausted,
    extract_json,
)

logger = logging.getLogger(__name__)


# --- Stage 1 weights --------------------------------------------------------
_W_ENTITY = 0.40
_W_GEO = 0.25
_W_TOPIC = 0.20
_W_INTRINSIC = 0.15

# Score-final tier cutoffs (mirror article tiers)
_TIER_T1 = 0.70
_TIER_T2 = 0.45
_TIER_T3 = 0.20  # below this = tier 0 (skipped from feed)

# Stage 2 minimum score gate
_STAGE2_MIN_SCORE = 0.25


# --- Stage 1: rules-based ---------------------------------------------------
def _entity_match_strength(
    user_entity_names: set[str],
    doc_entity_names: set[str],
    who_it_affects: list[str],
) -> tuple[float, list[str]]:
    """Return (component, list of matched canonical names).

    Includes intel.who_it_affects as a virtual entity set.
    """
    matched: list[str] = []
    doc_pool = {n.lower() for n in doc_entity_names} | {
        a.lower() for a in (who_it_affects or [])
    }
    for ue in user_entity_names:
        if ue.lower() in doc_pool:
            matched.append(ue)
    if not matched:
        return 0.0, []
    # Saturate at 5 matches - diminishing returns
    return min(1.0, len(matched) / 5.0), matched


def _geo_match_strength(
    user_geo_primary: str | None,
    user_geo_secondary: list[str],
    doc_geography_affected: list[str],
) -> float:
    """Return 0-1 based on overlap. Primary match = 1.0, secondary = 0.5, no match = 0."""
    if not doc_geography_affected:
        return 0.0
    doc_geos = {g.lower() for g in doc_geography_affected if g}
    if user_geo_primary and user_geo_primary.lower() in doc_geos:
        return 1.0
    if user_geo_secondary and any(
        s.lower() in doc_geos for s in user_geo_secondary if s
    ):
        return 0.5
    # India-wide docs partially relevant
    if "india" in doc_geos:
        return 0.3
    return 0.0


def _topic_priority(
    signal_priorities: dict, topic_category: str | None
) -> float:
    """signal_priorities is JSONB {topic: 1-10}. Return priority/10."""
    if not topic_category or not signal_priorities:
        return 0.0
    raw = signal_priorities.get(topic_category, 0)
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, val / 10.0))


def _coerce_jsonb(value: Any) -> Any:
    """asyncpg may return JSONB as str; normalise to py object."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def compute_stage1(
    *,
    user_entities: list[dict],
    user_profile: dict,
    doc: dict,
) -> dict[str, Any]:
    """Pure function - returns dict with score_stage1, components, matched names."""
    user_entity_names: set[str] = {
        ue["canonical_name"] for ue in user_entities if ue.get("canonical_name")
    }
    doc_entities = _coerce_jsonb(doc.get("entities_extracted")) or []
    doc_entity_names: set[str] = {
        e.get("name", "") for e in doc_entities if isinstance(e, dict) and e.get("name")
    }
    intel = _coerce_jsonb(doc.get("intel_json")) or {}
    who_it_affects = intel.get("who_it_affects", []) or []
    geography_affected = (
        _coerce_jsonb(doc.get("geography_affected"))
        or intel.get("geography_affected")
        or []
    )

    entity_strength, matched = _entity_match_strength(
        user_entity_names, doc_entity_names, who_it_affects
    )
    geo_strength = _geo_match_strength(
        user_profile.get("geo_primary"),
        user_profile.get("geo_secondary") or [],
        geography_affected,
    )
    topic_strength = _topic_priority(
        user_profile.get("signal_priorities") or {}, doc.get("topic_category")
    )
    intrinsic = float(doc.get("intrinsic_importance") or 0.0)

    score_stage1 = round(
        _W_ENTITY * entity_strength
        + _W_GEO * geo_strength
        + _W_TOPIC * topic_strength
        + _W_INTRINSIC * intrinsic,
        3,
    )

    return {
        "score_stage1": score_stage1,
        "entity_strength": round(entity_strength, 3),
        "geo_strength": round(geo_strength, 3),
        "topic_strength": round(topic_strength, 3),
        "intrinsic": intrinsic,
        "matched_entity_names": matched,
    }


# --- Stage 2: LLM -----------------------------------------------------------
_STAGE2_SYSTEM = """You are a policy intelligence analyst. Given a user profile and a structured government document intel, score how critical THIS document is for THIS user RIGHT NOW.

Return ONLY a JSON object:
{
  "score_final":         float 0-1 (critical = 1.0, irrelevant = 0.0; consider intrinsic importance + relevance to user),
  "urgency":             "HIGH" | "MEDIUM" | "LOW",
  "why_it_matters":      string (1-2 sentences, plain English, addressed to the user as "you"),
  "suggested_action":    string (concrete next step: "raise in next cabinet meeting" / "compare with prior GO X" / "ask analyst about Y"),
  "sentiment_for_user":  "FOR_USER" | "AGAINST_USER" | "NEUTRAL"
}

Rules:
- HIGH urgency = decision needed within 7 days OR contradicts user's known position
- MEDIUM = should know within 30 days
- LOW = situational awareness only"""


async def compute_stage2(
    *,
    user_profile: dict,
    user_entities: list[dict],
    intel: dict,
    doc_title: str,
    stage1_score: float,
) -> dict:
    """Groq call. Returns dict with score_final, urgency, why_it_matters, suggested_action, sentiment_for_user.

    Falls back to a degraded result on Groq error so caller can still cache something.
    """
    user_profile_summary = {
        "role_type": user_profile.get("role_type"),
        "role_context": user_profile.get("role_context"),
        "geo_primary": user_profile.get("geo_primary"),
        "geo_secondary": user_profile.get("geo_secondary"),
        "monitored_entities": [
            ue["canonical_name"]
            for ue in user_entities[:20]
            if ue.get("canonical_name")
        ],
    }
    user_msg = (
        f"USER PROFILE:\n{json.dumps(user_profile_summary, indent=2)}\n\n"
        f"DOCUMENT TITLE: {doc_title}\n\n"
        f"DOCUMENT INTEL:\n{json.dumps(intel, indent=2, default=str)}\n\n"
        f"Stage 1 deterministic score: {stage1_score:.3f}"
    )
    try:
        raw = await extract_json(
            system=_STAGE2_SYSTEM,
            user=user_msg,
            task_type="profile_extraction",
        )
        return {
            "score_final": float(raw.get("score_final", stage1_score)),
            "urgency": raw.get("urgency"),
            "why_it_matters": raw.get("why_it_matters"),
            "suggested_action": raw.get("suggested_action"),
            "sentiment_for_user": raw.get("sentiment_for_user"),
        }
    except (GroqQuotaExhausted, GroqCallFailed) as exc:
        logger.warning(
            "Stage 2 Groq failed for %r: %s", doc_title[:60], exc
        )
        return {
            "score_final": stage1_score,
            "urgency": None,
            "why_it_matters": None,
            "suggested_action": None,
            "sentiment_for_user": None,
        }
    except Exception as exc:  # noqa: BLE001 - defensive fallback
        logger.warning(
            "Stage 2 parse failed for %r: %s", doc_title[:60], exc
        )
        return {
            "score_final": stage1_score,
            "urgency": None,
            "why_it_matters": None,
            "suggested_action": None,
            "sentiment_for_user": None,
        }


def _tier_from_score(score_final: float) -> int:
    if score_final >= _TIER_T1:
        return 1
    if score_final >= _TIER_T2:
        return 2
    if score_final >= _TIER_T3:
        return 3
    return 0


# --- Top-level orchestrator -------------------------------------------------
async def score_govt_doc_for_user(
    *, db, doc_id: str, user_id: str
) -> dict:
    """Score one (doc, user) pair end to end. Caches into user_govt_doc_relevance.

    Returns the result dict. If a cached row exists and is fresh
    (cache.computed_at > doc.updated_at), returns cache without recomputing.
    """
    # --- Load inputs
    doc_row = (
        await db.execute(
            text(
                """
                SELECT id::text, title, topic_category, geo_primary,
                       intel_json, intrinsic_importance,
                       geography_affected, entities_extracted, updated_at
                FROM govt_documents WHERE id = CAST(:did AS uuid)
                """
            ),
            {"did": doc_id},
        )
    ).fetchone()
    if not doc_row:
        raise ValueError(f"Doc {doc_id} not found")

    user_profile_row = (
        await db.execute(
            text(
                """
                SELECT role_type, role_context, geo_primary,
                       geo_secondary, signal_priorities
                FROM user_profiles WHERE user_id = CAST(:uid AS uuid)
                """
            ),
            {"uid": user_id},
        )
    ).fetchone()
    if not user_profile_row:
        raise ValueError(f"User profile {user_id} not found")

    user_entities_rows = (
        await db.execute(
            text(
                """
                SELECT canonical_name, entity_type, priority
                FROM user_entities
                WHERE user_id = CAST(:uid AS uuid)
                ORDER BY priority DESC LIMIT 50
                """
            ),
            {"uid": user_id},
        )
    ).fetchall()

    # Check cache freshness
    cached = (
        await db.execute(
            text(
                """
                SELECT score_final, urgency, why_it_matters, suggested_action,
                       sentiment_for_user, matched_entity_names,
                       score_stage1, relevance_tier, computed_at
                FROM user_govt_doc_relevance
                WHERE user_id = CAST(:uid AS uuid)
                  AND doc_id = CAST(:did AS uuid)
                """
            ),
            {"uid": user_id, "did": doc_id},
        )
    ).fetchone()

    if (
        cached
        and cached.computed_at
        and doc_row.updated_at
        and cached.computed_at > doc_row.updated_at
    ):
        return {
            "score_final": cached.score_final,
            "urgency": cached.urgency,
            "why_it_matters": cached.why_it_matters,
            "suggested_action": cached.suggested_action,
            "sentiment_for_user": cached.sentiment_for_user,
            "matched_entity_names": cached.matched_entity_names,
            "score_stage1": cached.score_stage1,
            "relevance_tier": cached.relevance_tier,
            "cached": True,
        }

    # --- Stage 1
    intel_parsed = _coerce_jsonb(doc_row.intel_json) or {}
    doc_dict = {
        "topic_category": doc_row.topic_category,
        "geo_primary": doc_row.geo_primary,
        "intel_json": intel_parsed,
        "intrinsic_importance": doc_row.intrinsic_importance,
        "geography_affected": doc_row.geography_affected,
        "entities_extracted": doc_row.entities_extracted,
    }
    user_profile = {
        "role_type": user_profile_row.role_type,
        "role_context": user_profile_row.role_context,
        "geo_primary": user_profile_row.geo_primary,
        "geo_secondary": list(user_profile_row.geo_secondary or []),
        "signal_priorities": _coerce_jsonb(
            user_profile_row.signal_priorities
        )
        or {},
    }
    user_entities = [
        {
            "canonical_name": r.canonical_name,
            "entity_type": r.entity_type,
            "priority": r.priority,
        }
        for r in user_entities_rows
    ]

    s1 = compute_stage1(
        user_entities=user_entities,
        user_profile=user_profile,
        doc=doc_dict,
    )

    # --- Stage 2 only if Stage 1 passes threshold
    if s1["score_stage1"] >= _STAGE2_MIN_SCORE:
        s2 = await compute_stage2(
            user_profile=user_profile,
            user_entities=user_entities,
            intel=intel_parsed,
            doc_title=doc_row.title,
            stage1_score=s1["score_stage1"],
        )
    else:
        s2 = {
            "score_final": s1["score_stage1"],
            "urgency": "LOW",
            "why_it_matters": None,
            "suggested_action": None,
            "sentiment_for_user": "NEUTRAL",
        }

    score_final = float(s2["score_final"])
    tier = _tier_from_score(score_final)

    # --- Upsert cache
    await db.execute(
        text(
            """
            INSERT INTO user_govt_doc_relevance (
              user_id, doc_id, score_stage1, score_final, relevance_tier,
              urgency, why_it_matters, suggested_action, sentiment_for_user,
              matched_entity_names, geo_match_strength, computed_at
            ) VALUES (
              CAST(:uid AS uuid), CAST(:did AS uuid), :s1, :sf, :tier,
              :urg, :why, :act, :sent,
              :matched, :geo_str, NOW()
            )
            ON CONFLICT (user_id, doc_id) DO UPDATE SET
              score_stage1         = EXCLUDED.score_stage1,
              score_final          = EXCLUDED.score_final,
              relevance_tier       = EXCLUDED.relevance_tier,
              urgency              = EXCLUDED.urgency,
              why_it_matters       = EXCLUDED.why_it_matters,
              suggested_action     = EXCLUDED.suggested_action,
              sentiment_for_user   = EXCLUDED.sentiment_for_user,
              matched_entity_names = EXCLUDED.matched_entity_names,
              geo_match_strength   = EXCLUDED.geo_match_strength,
              computed_at          = NOW()
            """
        ),
        {
            "uid": user_id,
            "did": doc_id,
            "s1": s1["score_stage1"],
            "sf": score_final,
            "tier": tier,
            "urg": s2["urgency"],
            "why": s2["why_it_matters"],
            "act": s2["suggested_action"],
            "sent": s2["sentiment_for_user"],
            "matched": s1["matched_entity_names"],
            "geo_str": s1["geo_strength"],
        },
    )
    await db.commit()

    return {
        "score_final": score_final,
        "urgency": s2["urgency"],
        "why_it_matters": s2["why_it_matters"],
        "suggested_action": s2["suggested_action"],
        "sentiment_for_user": s2["sentiment_for_user"],
        "matched_entity_names": s1["matched_entity_names"],
        "score_stage1": s1["score_stage1"],
        "relevance_tier": tier,
        "cached": False,
    }
