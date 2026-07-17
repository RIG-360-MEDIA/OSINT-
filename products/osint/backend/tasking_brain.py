"""Tasking brain — keyword -> classification -> justified source plan.

The intelligence core: given a keyword, decide WHAT it is (person / organization /
location / topic) and therefore WHICH sources are worth searching. A person pulls
social + network + images; an organization pulls registries + infra; a location
pulls the map; a niche topic pulls academic/company/data.

Classification is grounded in RIG's own `entity_dictionary` (19,385 entities with
type + aliases + party/country) — exact canonical-or-alias match. No dictionary
match => it's a free-text topic. (Validated: modi->person, reliance->organization,
hyderabad->location, semiconductor->topic.)

`status` on each planned source is honest: 'live' = RIG collects/serves it today;
'planned' = on the roadmap (feature-map), not wired yet.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

# type -> ordered source plan. Each: (source, priority, status, reason).
SOURCE_PLANS: dict[str, list[tuple[str, str, str, str]]] = {
    "person": [
        ("articles", "high", "live", "primary coverage of the individual"),
        ("social", "high", "live", "what they and others say across platforms"),
        ("sentiment", "high", "live", "directed stance toward the person"),
        ("related_entities", "high", "live", "who/what they appear alongside"),
        ("network", "med", "planned", "amplifiers, allies, coordination (SNA)"),
        ("images", "med", "planned", "reverse-image / appearances / geolocation"),
        ("company", "med", "planned", "business & financial ties if applicable"),
        ("documents", "low", "planned", "filings, court records, affidavits"),
    ],
    "organization": [
        ("articles", "high", "live", "coverage of the organization"),
        ("company_registry", "high", "planned", "official records, owners, officers"),
        ("social", "high", "live", "org messaging + public chatter"),
        ("sentiment", "med", "live", "stance toward the org"),
        ("infra", "med", "planned", "domains/servers/shared-infrastructure"),
        ("financial", "med", "planned", "filings, procurement, trade flows"),
        ("related_entities", "med", "live", "connected people & orgs"),
    ],
    "location": [
        ("articles", "high", "live", "local + national coverage"),
        ("map_districts", "high", "live", "district situation map (AP/TG live; other regions planned)"),
        ("social", "med", "live", "local chatter & sentiment"),
        ("sentiment", "med", "live", "mood in/about the place"),
        ("related_entities", "med", "live", "people/orgs/events tied to the place"),
        ("geospatial", "low", "planned", "satellite / imagery / change-detection"),
    ],
    "topic": [
        ("articles", "high", "live", "coverage of the topic"),
        ("social", "med", "live", "public discussion & sentiment"),
        ("related_entities", "high", "live", "the orgs/people/places driving the topic"),
        ("sentiment", "med", "live", "how the topic is framed"),
        ("academic", "med", "planned", "research/patents/capability signal"),
        ("company", "med", "planned", "companies active in the space"),
        ("data_stats", "low", "planned", "hard-number grounding"),
    ],
}

# ambiguity tie-break: a bare keyword is most often a person, then org, then place.
_PRIORITY = ["person", "organization", "location"]


async def classify_keyword(db, q: str) -> dict[str, Any]:
    """Classify a keyword via exact canonical-or-alias dictionary match."""
    q = (q or "").strip()
    if not q:
        return {"type": "topic", "method": "empty", "matches": []}
    rows = (await db.execute(text("""
        SELECT d.entity_type AS et, d.canonical_name AS cn,
               d.party AS party, d.country AS country, d.state AS state
          FROM entity_dictionary d
         WHERE lower(d.canonical_name) = lower(:q)
            OR EXISTS (SELECT 1 FROM unnest(d.aliases) a WHERE lower(a) = lower(:q))
         -- disambiguation tie-break: India-relevant first (product is India-primary),
         -- then more-aliases (prominence proxy), then shorter canonical.
         ORDER BY (d.country = 'IN') DESC NULLS LAST,
                  coalesce(array_length(d.aliases, 1), 0) DESC,
                  length(d.canonical_name) ASC
         LIMIT 25
    """), {"q": q})).fetchall()

    if not rows:
        return {"type": "topic", "method": "no-dictionary-match",
                "ambiguous": False, "matches": [], "party": None,
                "country": None, "state": None}

    by_type: dict[str, list[str]] = {}
    for r in rows:
        by_type.setdefault(r.et, []).append(r.cn)
    dominant = next((t for t in _PRIORITY if t in by_type), next(iter(by_type)))
    meta = next((r for r in rows if r.et == dominant), rows[0])
    return {
        "type": dominant,
        "ambiguous": len(by_type) > 1,
        "all_types": by_type,
        "canonical": meta.cn,
        "party": meta.party,
        "country": meta.country,
        "state": meta.state,
        "method": "dictionary",
    }


async def build_task_plan(db, q: str) -> dict[str, Any]:
    """Keyword -> classification + the justified source plan + default perspective."""
    c = await classify_keyword(db, q)
    plan = SOURCE_PLANS.get(c["type"], SOURCE_PLANS["topic"])
    # perspective default: India when the entity is Indian (country IN or has a state).
    if c.get("country") == "IN" or c.get("state"):
        perspective = "india"
    else:
        perspective = (c.get("country") or "global")
    return {
        "query": q,
        "classification": c,
        "perspective_default": perspective,
        "source_plan": [
            {"source": s, "priority": p, "status": st, "reason": r}
            for (s, p, st, r) in plan
        ],
    }
