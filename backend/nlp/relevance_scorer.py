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


# Soft-saturation constant for v2: a single high-prominence primary lands ~0.62;
# additional matched entities keep adding with diminishing returns (asymptote <1).
_V2_SAT_C = 0.6
_V2_PROMINENCE_FLOOR = 0.15  # a watched entity mentioned in passing still registers


def compute_entity_score_v2(
    entities_extracted: list,
    user_entities: list,
) -> float:
    """v2 entity match — fixes the v1 hard-cap-at-~2 saturation.

    Per matched watched entity:
        contribution = max(prominence, FLOOR) × (priority/10)²
    then SOFT saturation: score = Σ / (Σ + C).

    Changes vs v1:
    - priority is SQUARED → primary (10) ≈ 4× a mid (5); secondaries still count.
    - count genuinely matters: 5 matched entities > 3 > 1 (no flat cap at 2).
    - prominence FLOOR: a watched entity named in passing (prominence 0) no longer
      contributes exactly zero — it registers a little (~39% of mentions sit at 0).
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
            prominence = max(article_map[name].get("prominence", 0.5), _V2_PROMINENCE_FLOOR)
            pr = ue.get("priority", 5) / 10.0
            total += prominence * (pr * pr)

    return total / (total + _V2_SAT_C)


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
    entity_scorer=compute_entity_score_v2,  # v2 default (A/B-validated 2026-06-12: fixes flat-cap inversion for multi-entity users, no threshold change). Pass compute_entity_score for legacy v1.
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

    entity_score = entity_scorer(entities, user_entities)
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


# ── v3: canonicalization (#1) + geo word-boundary (#2) + recency (#3) + muting (#8) ──

import math
import re
from datetime import datetime, timezone

_WORD_RE: dict[str, "re.Pattern"] = {}


def _canon(name: str | None, alias_map: dict) -> str:
    """Normalize an entity name to its canonical form via the alias map (#1).
    'kcr' / 'k. chandrashekar rao' → the same canonical key. Empty map = identity."""
    n = (name or "").strip().lower()
    return alias_map.get(n, n) if alias_map else n


def _word_match(term: str, text: str) -> bool:
    """Word-boundary containment (#2): 'india' matches 'India' but NOT 'Indiana'."""
    if not term or not text:
        return False
    pat = _WORD_RE.get(term)
    if pat is None:
        pat = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
        _WORD_RE[term] = pat
    return bool(pat.search(text))


def compute_entity_score_v3(entities_extracted: list, user_entities: list, alias_map: dict | None = None) -> float:
    """v2 entity scoring + canonicalization (#1): both sides normalized through the
    alias map before matching, so name variants of a watched entity still hit."""
    if not entities_extracted or not user_entities:
        return 0.0
    am = alias_map or {}
    article_map: dict[str, dict] = {}
    for e in entities_extracted:
        nm = e.get("name")
        if nm and nm != "None":
            article_map[_canon(nm, am)] = e
    total = 0.0
    for ue in user_entities:
        cname = _canon(ue["canonical_name"], am)
        if cname in article_map:
            prominence = max(article_map[cname].get("prominence", 0.5), _V2_PROMINENCE_FLOOR)
            pr = ue.get("priority", 5) / 10.0
            total += prominence * (pr * pr)
    return total / (total + _V2_SAT_C)


def compute_geo_score_v3(article_geo_primary, user_geo_primary, user_geo_secondary) -> float:
    """Geo match with WORD-BOUNDARY containment (#2) — no 'India' inside 'Indiana'."""
    if not article_geo_primary:
        return 0.0
    ag = article_geo_primary
    if user_geo_primary:
        if ag.lower() == user_geo_primary.lower():
            return 1.0
        if _word_match(user_geo_primary, ag) or _word_match(ag, user_geo_primary):
            return 0.5
    for sec in (user_geo_secondary or []):
        if ag.lower() == sec.lower():
            return 0.7
        if _word_match(sec, ag) or _word_match(ag, sec):
            return 0.4
    return 0.0


def compute_geo_multiplier_v3(article_title, article_text, user_geo_primary, user_geo_secondary) -> float:
    """Geo title/body boost, word-boundary matched (#2)."""
    if not user_geo_primary:
        return 1.0
    terms = [user_geo_primary] + list(user_geo_secondary or [])
    title = article_title or ""
    body = (article_text or "")[:500]
    if any(_word_match(t, title) for t in terms):
        return 1.5
    if any(_word_match(t, body) for t in terms):
        return 1.0
    return 0.4


_RECENCY_HALFLIFE_H = 24.0
_RECENCY_FLOOR = 0.5


def compute_recency_multiplier(published_at, now=None, halflife_h: float = _RECENCY_HALFLIFE_H,
                               floor: float = _RECENCY_FLOOR) -> float:
    """Recency decay (#3): 1.0 at age 0, halves every `halflife_h`, floored so an
    older-but-on-topic story isn't crushed. Missing timestamp → neutral 1.0."""
    if not published_at:
        return 1.0
    now = now or datetime.now(timezone.utc)
    try:
        age_h = max((now - published_at).total_seconds() / 3600.0, 0.0)
    except Exception:  # noqa: BLE001
        return 1.0
    return floor + (1.0 - floor) * math.pow(0.5, age_h / halflife_h)


def compute_stage1_score_v3(
    article: dict,
    user_profile: dict,
    user_entities: list,
    source_geo_states: list,
    alias_map: dict | None = None,
    muted_entities: set | None = None,
    muted_sources: set | None = None,
    now=None,
    apply_recency: bool = True,
) -> tuple[float, dict]:
    """v3 Stage-1 = v2 geometry + canonicalized entities (#1) + geo word-boundary (#2)
    + recency decay (#3) + muting/anti-preferences (#8). Per-user adaptive tiers (#7)
    and cluster-dedup (#5) are applied at FEED ASSEMBLY, not here."""
    am = alias_map or {}
    muted_e = muted_entities or set()
    muted_s = muted_sources or set()
    ents = article.get("entities_extracted", []) or []

    # ---- muting (#8): a muted source, or a PROMINENT muted entity, suppresses the article
    src_name = (article.get("source_name") or "").strip().lower()
    if src_name and src_name in muted_s:
        return 0.0, {"muted": "source"}
    for e in ents:
        if _canon(e.get("name"), am) in muted_e and (e.get("prominence") or 0) >= 0.6:
            return 0.0, {"muted": "entity"}

    title = article.get("title", "")
    text = article.get("lead_text_translated", "") or article.get("lead_text_original", "") or ""
    topic = article.get("topic_category", "")
    geo_primary = article.get("geo_primary")
    source_tier = article.get("source_tier", 2)

    signal_priorities = user_profile.get("signal_priorities", {})
    user_geo_primary = user_profile.get("geo_primary", "") or ""
    user_geo_secondary = user_profile.get("geo_secondary", []) or []
    user_entity_names = {ue["canonical_name"] for ue in user_entities}
    confidence_weight = 0.5 if article.get("nlp_confidence") == "low" else 1.0

    entity_score = compute_entity_score_v3(ents, user_entities, am)
    max_matched_priority = _max_matched_entity_priority(ents, user_entities)
    topic_score = compute_topic_score(topic, signal_priorities)
    topic_gate = compute_topic_gate(topic, title, user_entity_names)
    geo_score = compute_geo_score_v3(geo_primary, user_geo_primary, user_geo_secondary)
    source_score = compute_source_score(source_tier)
    geo_multiplier = compute_geo_multiplier_v3(title, text, user_geo_primary, user_geo_secondary)
    source_bonus = compute_source_geo_bonus(source_geo_states, user_geo_primary)

    effective_gate = topic_gate
    if topic == "INTERNATIONAL" and max_matched_priority >= 5:
        effective_gate = 1.0
    if topic == "POLITICS" and entity_score == 0.0 and geo_score == 0.0 and geo_multiplier == 0.4:
        effective_gate = min(effective_gate, 0.4)

    entity_component = 0.40 * entity_score * effective_gate
    non_entity_component = (0.25 * topic_score + 0.20 * geo_score + 0.15 * source_score) * effective_gate
    final = entity_component + (non_entity_component * geo_multiplier) + source_bonus
    final = final * confidence_weight

    recency_mult = compute_recency_multiplier(article.get("published_at"), now) if apply_recency else 1.0
    final = min(final * recency_mult, 1.0)

    debug = {
        "entity_score": round(entity_score, 3), "geo_score": round(geo_score, 3),
        "geo_multiplier": geo_multiplier, "effective_gate": effective_gate,
        "recency_mult": round(recency_mult, 3), "final": round(final, 3),
    }
    return final, debug


def adaptive_tier(score: float, user_score_p50: float | None = None, user_score_p80: float | None = None) -> int:
    """Per-user-adaptive tiering (#7): if the user's own score distribution is known,
    tier by their personal p80/p50 (a niche-entity user with sparse matches still gets a
    feed; a flooded user gets a stricter bar). Falls back to the global 0.50/0.25/0.10."""
    if user_score_p80 is not None and user_score_p50 is not None and user_score_p80 > 0:
        if score >= user_score_p80:
            return 1
        if score >= user_score_p50:
            return 2
        if score >= max(0.10, 0.5 * user_score_p50):
            return 3
        return 0
    if score >= 0.50:
        return 1
    if score >= 0.25:
        return 2
    if score >= 0.10:
        return 3
    return 0


def dedup_by_cluster(scored: list[dict], story_of: dict, keep: str = "max") -> list[dict]:
    """Cluster-dedup (#5): collapse same-story articles (story_of[article_id]) to ONE card,
    keeping the highest-scoring representative. Articles with no story_id pass through.
    `scored` items must have 'id' and 'score'. Returns the deduped, score-sorted list."""
    best: dict[str, dict] = {}
    passthrough: list[dict] = []
    for item in scored:
        sid = story_of.get(item["id"])
        if not sid:
            passthrough.append(item)
            continue
        cur = best.get(sid)
        if cur is None or item["score"] > cur["score"]:
            if cur is not None:
                item["_collapsed"] = cur.get("_collapsed", 0) + 1
            best[sid] = item
        else:
            cur["_collapsed"] = cur.get("_collapsed", 0) + 1
    out = passthrough + list(best.values())
    out.sort(key=lambda x: -x["score"])
    return out


# ── Stage 2 ───────────────────────────────────────────────────────────────────


async def compute_stage2_explanation(
    article: dict,
    user_profile: dict,
    stage1_score: float | None = None,
) -> dict:
    """
    Groq generates a per-user relevance explanation + final score.

    Dispatch gate (in ``tasks/relevance_task.py:213``):
        Stage 2 runs only when ``stage1_score >= 0.25`` AND ``tier > 0``,
        i.e. tier-1 (score >= 0.50) and tier-2 (0.25 <= score < 0.50).
        Tier-3 (0.10 <= score < 0.25) and tier-0 (< 0.10) **do not** call
        Groq — their ``relevance_explanation`` stays NULL by design. Coverage
        audit C-5 (2026-04-28) documents this here so a future reader does
        not try to "fix" the missing tier-3/0 explanations.

    Tier mapping (applied to either Stage 1 or Stage 2 score):
        score >= 0.50 → tier 1
        score >= 0.25 → tier 2
        score >= 0.10 → tier 3
        else          → tier 0  (suppressed from feed)

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
        # #4: on LLM failure, fall back to the careful Stage-1 algorithmic score
        # (NOT a flat 0.3 vibe-number layered on a structured one). Only default to
        # 0.3 if Stage 1 wasn't provided.
        logger.warning("Stage 2 failed: %s — falling back to Stage-1 score", e)
        fallback = stage1_score if stage1_score is not None else 0.3
        return {
            "score": float(fallback),
            "explanation": "Relevant to your monitored topics.",
            "sentiment_for_user": "NEUTRAL",
        }
