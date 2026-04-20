"""
Two-stage relevance scoring engine.

Stage 1 — algorithmic, runs on all articles.
Stage 2 — Groq explanation, runs only for Stage 1 score >= 0.25.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# ── Stage 1 helpers ───────────────────────────────────────────────────────────


def compute_entity_score(
    entities_extracted: list,
    user_entities: list,
) -> float:
    """
    Prominence-weighted entity match.

    contribution = prominence × (priority / 10)
    score = min(sum(contributions) / 2.0, 1.0)
    """
    if not entities_extracted or not user_entities:
        return 0.0

    article_map = {
        e["name"].lower(): e
        for e in entities_extracted
        if e.get("name") and e["name"] != "None"
    }

    total = 0.0
    for ue in user_entities:
        name = ue["canonical_name"].lower()
        if name in article_map:
            prominence = article_map[name].get("prominence", 0.5)
            priority = ue.get("priority", 5) / 10.0
            total += prominence * priority

    return min(total / 2.0, 1.0)


def compute_topic_score(
    topic_category: str,
    signal_priorities: dict,
) -> float:
    """priority / 10 for this topic; default 0.5 when unknown."""
    if not topic_category:
        return 0.5
    return signal_priorities.get(topic_category, 5) / 10.0


def compute_topic_gate(
    topic_category: str,
    article_title: str,
    user_entity_names: set,
) -> float:
    """
    SPORTS → 0.1 unless a watched entity appears in the title.
    INTERNATIONAL → 0.3 to reduce foreign-news noise in the scored pool.
    """
    if topic_category == "SPORTS":
        title_lower = (article_title or "").lower()
        for name in user_entity_names:
            if name.lower() in title_lower:
                return 1.0
        return 0.1

    if topic_category == "INTERNATIONAL":
        return 0.3

    return 1.0


def compute_geo_score(
    article_geo_primary: str | None,
    user_geo_primary: str,
    user_geo_secondary: list,
) -> float:
    """
    1.0 — exact match with user's primary state/city
    0.7 — match with secondary location
    0.5 — article geo contained within user's primary (district in state)
    0.4 — partial secondary match
    0.0 — no match or NULL
    """
    if not article_geo_primary:
        return 0.0

    ag = article_geo_primary.lower()

    if user_geo_primary:
        up = user_geo_primary.lower()
        if ag == up:
            return 1.0
        if up in ag or ag in up:
            return 0.5

    for sec in (user_geo_secondary or []):
        sl = sec.lower()
        if ag == sl:
            return 0.7
        if sl in ag or ag in sl:
            return 0.4

    return 0.0


def compute_geo_multiplier(
    article_title: str,
    article_text: str,
    user_geo_primary: str,
    user_geo_secondary: list,
) -> float:
    """
    1.5 — user's state/city in article TITLE
    1.0 — in first 500 chars of body
    0.4 — not found anywhere
    1.0 (neutral) — when user has no geo_primary
    """
    if not user_geo_primary:
        return 1.0

    terms = [user_geo_primary.lower()] + [
        s.lower() for s in (user_geo_secondary or [])
    ]
    title_l = (article_title or "").lower()
    body_start = (article_text or "")[:500].lower()

    for term in terms:
        if term in title_l:
            return 1.5

    for term in terms:
        if term in body_start:
            return 1.0

    return 0.4


def compute_source_score(source_tier: int | None) -> float:
    """Tier 1 → 1.0, Tier 2 → 0.7, Tier 3 → 0.4, unknown → 0.5"""
    return {1: 1.0, 2: 0.7, 3: 0.4}.get(source_tier or 2, 0.5)


def compute_source_geo_bonus(
    source_geo_states: list,
    user_geo_primary: str,
) -> float:
    """
    +0.15 — source focuses on user's state
    +0.05 — source covers India
    +0.00 — all other sources
    """
    if not source_geo_states or not user_geo_primary:
        return 0.0

    states_lower = [s.lower() for s in source_geo_states]

    if user_geo_primary.lower() in states_lower:
        return 0.15

    if "india" in states_lower:
        return 0.05

    return 0.0


def _max_matched_entity_priority(
    entities_extracted: list,
    user_entities: list,
) -> int:
    """Return the highest watch-list priority among entities that appear in the article."""
    if not entities_extracted or not user_entities:
        return 0
    article_names = {
        e["name"].lower()
        for e in entities_extracted
        if e.get("name") and e["name"] != "None"
    }
    return max(
        (ue.get("priority", 0) for ue in user_entities if ue["canonical_name"].lower() in article_names),
        default=0,
    )


def compute_stage1_score(
    article: dict,
    user_profile: dict,
    user_entities: list,
    source_geo_states: list,
) -> tuple[float, dict]:
    """
    Compute Stage 1 algorithmic relevance score.
    Returns (score, debug_info).

    Key design:
    - Entity component is NOT geo-penalised: a story about a watched person is
      relevant regardless of whether "Telangana" appears in the extracted text.
    - Non-entity components (topic, geo, source) ARE geo-weighted.
    - POLITICS articles with no entity match and no geo anchor are treated like
      INTERNATIONAL to prevent international politics flooding the scored pool.
    """
    title = article.get("title", "")
    text = (
        article.get("lead_text_translated", "")
        or article.get("lead_text_original", "")
        or ""
    )
    topic = article.get("topic_category", "")
    geo_primary = article.get("geo_primary")
    source_tier = article.get("source_tier", 2)
    entities = article.get("entities_extracted", [])

    signal_priorities = user_profile.get("signal_priorities", {})
    user_geo_primary = user_profile.get("geo_primary", "") or ""
    user_geo_secondary = user_profile.get("geo_secondary", []) or []

    user_entity_names = {ue["canonical_name"] for ue in user_entities}

    confidence_weight = (
        0.5 if article.get("nlp_confidence") == "low" else 1.0
    )

    entity_score = compute_entity_score(entities, user_entities)
    max_matched_priority = _max_matched_entity_priority(entities, user_entities)

    topic_score = compute_topic_score(topic, signal_priorities)
    topic_gate = compute_topic_gate(topic, title, user_entity_names)
    geo_score = compute_geo_score(geo_primary, user_geo_primary, user_geo_secondary)
    source_score = compute_source_score(source_tier)
    geo_multiplier = compute_geo_multiplier(title, text, user_geo_primary, user_geo_secondary)
    source_bonus = compute_source_geo_bonus(source_geo_states, user_geo_primary)

    # INTERNATIONAL bypass: high-priority entity in a foreign-tagged article is still relevant
    effective_gate = topic_gate
    if topic == "INTERNATIONAL" and max_matched_priority >= 5:
        effective_gate = 1.0

    # POLITICS with no entity anchor and no geo anchor → treat like INTERNATIONAL noise
    if (
        topic == "POLITICS"
        and entity_score == 0.0
        and geo_score == 0.0
        and geo_multiplier == 0.4
    ):
        effective_gate = min(effective_gate, 0.4)

    # Entity component is geo-independent: a watched-entity story is relevant
    # even when the article text doesn't mention the user's state explicitly.
    entity_component = 0.40 * entity_score * effective_gate
    non_entity_component = (
        0.25 * topic_score + 0.20 * geo_score + 0.15 * source_score
    ) * effective_gate

    final = entity_component + (non_entity_component * geo_multiplier) + source_bonus
    final = final * confidence_weight
    final = min(final, 1.0)

    debug = {
        "entity_score": round(entity_score, 3),
        "max_matched_priority": max_matched_priority,
        "topic_score": round(topic_score, 3),
        "geo_score": round(geo_score, 3),
        "source_score": round(source_score, 3),
        "topic_gate": topic_gate,
        "effective_gate": effective_gate,
        "geo_multiplier": geo_multiplier,
        "source_bonus": source_bonus,
        "entity_component": round(entity_component, 3),
        "non_entity_component": round(non_entity_component, 3),
        "final": round(final, 3),
        "confidence_weight": confidence_weight,
    }

    return final, debug


# ── Stage 2 ───────────────────────────────────────────────────────────────────


async def compute_stage2_explanation(
    article: dict,
    user_profile: dict,
) -> dict:
    """
    Groq generates relevance explanation for articles scoring >= 0.25 in Stage 1.
    Uses FAST_MODEL (llama-3.1-8b-instant) — classification, not generation.
    Returns {score, explanation, sentiment_for_user}.
    """
    from backend.nlp.groq_client import extract_json

    system = (
        "You are assessing article relevance for a specific person.\n"
        "Reply with JSON only. No markdown.\n"
        "Output exactly:\n"
        '{"score": <float 0.0-1.0>, '
        '"explanation": "<one sentence why this matters to this person>", '
        '"sentiment": "<FOR_USER|AGAINST_USER|NEUTRAL>"}'
    )

    lead = (
        article.get("lead_text_translated")
        or article.get("lead_text_original")
        or ""
    )[:500]

    user_msg = (
        f"Person: {user_profile.get('role_context', '')}\n"
        f"They monitor: {user_profile.get('geo_primary', '')}, "
        f"governance, key entities\n\n"
        f"Article: {article.get('title', '')}\n"
        f"Text: {lead}"
    )

    try:
        result = await extract_json(
            system=system,
            user=user_msg,
            task_type="relevance_explanation",
        )
        return {
            "score": float(result.get("score", 0.5)),
            "explanation": str(result.get("explanation", ""))[:500],
            "sentiment_for_user": result.get("sentiment", "NEUTRAL"),
        }
    except Exception as e:
        logger.warning("Stage 2 failed: %s", e)
        return {
            "score": 0.3,
            "explanation": "Relevant to your monitored topics.",
            "sentiment_for_user": "NEUTRAL",
        }
