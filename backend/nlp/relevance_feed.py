"""Feed assembly — turns per-article v3 relevance scores into a per-user feed.

Ties together the feature-level relevance points that operate at ASSEMBLY (not per-article):
  #5 cluster-dedup     — collapse the 12 outlets covering one story to ONE card
  #7 adaptive tiers    — tier by the user's OWN score distribution, not a global 0.50/0.25
  #6 discovery lane    — a serendipity slot: emerging/adjacent stories the user does NOT
                         watch but that matter in topics they care about

The per-article ranking is `compute_stage1_score_v3` (canonicalization/geo-wb/recency/muting).
"""
from __future__ import annotations

from backend.nlp.relevance_scorer import (
    compute_stage1_score_v3,
    compute_recency_multiplier,
    compute_source_score,
    adaptive_tier,
    dedup_by_cluster,
)

_DISCOVERY_MIN_TOPIC_PRIORITY = 0.6
_DISCOVERY_MIN_ENTITIES = 4


def discovery_candidates(pool: list, user_profile: dict, seen_stories: set, story_of: dict,
                         limit: int = 3) -> list[dict]:
    """#6: from articles with NO watched-entity match, surface the emerging/adjacent ones —
    high topic-priority × recency × source quality × breadth (many entities = a real story),
    excluding clusters already in the main feed. The 'you didn't ask for this but it's
    blowing up in your area' lane. Returns up to `limit` items."""
    sp = user_profile.get("signal_priorities", {}) or {}
    ranked = []
    for a in pool:
        sid = story_of.get(a["id"])
        if sid and sid in seen_stories:
            continue  # already represented in the matched feed
        topic = a.get("topic_category", "") or ""
        topic_pri = sp.get(topic, 5) / 10.0
        if topic_pri < _DISCOVERY_MIN_TOPIC_PRIORITY:
            continue
        n_ent = len(a.get("entities_extracted", []) or [])
        if n_ent < _DISCOVERY_MIN_ENTITIES:
            continue  # thin/listicle items aren't emerging stories
        rec = compute_recency_multiplier(a.get("published_at"))
        src = compute_source_score(a.get("source_tier", 2))
        disc = topic_pri * rec * (0.5 + 0.5 * src) * min(1.0, n_ent / 8.0)
        ranked.append({
            "id": a["id"], "discovery_score": round(disc, 3), "is_discovery": True,
            "topic": topic, "title": (a.get("title") or "")[:90],
        })
    ranked.sort(key=lambda x: -x["discovery_score"])
    return ranked[:limit]


def assemble_feed(
    articles: list,
    user_profile: dict,
    user_entities: list,
    *,
    alias_map: dict | None = None,
    muted_entities: set | None = None,
    muted_sources: set | None = None,
    story_of: dict | None = None,
    source_geo_states: list | None = None,
    now=None,
    discovery_slots: int = 3,
) -> dict:
    """Score (v3) → split matched vs unmatched → dedup matched by cluster (#5) →
    per-user adaptive tiers (#7) → inject a discovery lane from the unmatched pool (#6).

    Returns {feed: [...], discovery: [...], thresholds: {...}}. Each feed item:
    {id, score, tier, collapsed (#stories merged into this card), a}.
    """
    story_of = story_of or {}
    matched, unmatched = [], []
    for a in articles:
        score, dbg = compute_stage1_score_v3(
            a, user_profile, user_entities, source_geo_states or [],
            alias_map=alias_map, muted_entities=muted_entities,
            muted_sources=muted_sources, now=now,
        )
        if dbg.get("muted"):
            continue  # #8: muted source/entity drops out entirely
        if dbg.get("entity_score", 0.0) > 0.0:
            matched.append({"id": a["id"], "score": score, "a": a})
        else:
            unmatched.append(a)

    # #5 — collapse same-story duplicates to one representative card
    deduped = dedup_by_cluster(matched, story_of)

    # #7 — tier by THIS user's own score distribution (niche user still gets a feed;
    #      flooded user gets a stricter bar) with a global fallback inside adaptive_tier
    vals = sorted(x["score"] for x in deduped if x["score"] > 0)
    p50 = vals[len(vals) // 2] if vals else None
    p80 = vals[int(len(vals) * 0.8)] if vals else None
    for x in deduped:
        x["tier"] = adaptive_tier(x["score"], p50, p80)
        x["collapsed"] = x.get("_collapsed", 0)

    feed = sorted((x for x in deduped if x["tier"] > 0), key=lambda x: -x["score"])

    # #6 — discovery lane from the no-watched-entity pool
    seen_stories = {story_of.get(x["id"]) for x in feed if story_of.get(x["id"])}
    discovery = discovery_candidates(unmatched, user_profile, seen_stories, story_of, discovery_slots)

    return {"feed": feed, "discovery": discovery, "thresholds": {"p50": p50, "p80": p80}}
