"""Shared loader for a user's saved brief preferences.

Reads ``analytics.user_brief_prefs`` and normalises the JSONB columns. Used by
every personalised brief block (executive, cm_perspective, stories) so the
shape is defined once.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text


def jsonify(v: Any) -> dict:
    """Coerce a JSONB column (dict or JSON string) into a dict; {} if null."""
    if v is None:
        return {}
    return v if isinstance(v, dict) else json.loads(v)


async def load_prefs(db, uid: str) -> dict[str, Any] | None:
    """Return the user's brief prefs, with entity IDs auto-resolved through redirects.

    Every entity_id referenced (primary_subject_id, primary_subject_meta.id +
    .also[].id, watchlist.entity_ids[]) is walked through
    `entity_dictionary.redirected_to` on each read. So when the entity-dict
    consolidation pass redirects a row (Tier 1/2/3 dupe-merging), personas keep
    working transparently — no remap migration on user_brief_prefs ever needed.
    Chains are flattened to <=1 hop by migration 096; the single lookup suffices,
    and any future chain settles eventually-consistently across requests.

    Collapsed pairs (e.g. "Pawan Kalyan" + "K. Pawan Kalyan" both in a watchlist
    when Tier 3 merges them) are deduplicated post-resolution so the engines
    don't double-count.

    NOTE: the onboarding wizard folds the "purpose" step (use_cases + llm_tone)
    into `personality`, so purpose is read via prefs["personality"], not a
    separate key.
    """
    row = (await db.execute(text("""
        SELECT primary_subject_id::text AS psid, primary_subject_meta,
               watchlist, regions, topics,
               languages, stance, personality, events, sources, delivery
          FROM analytics.user_brief_prefs WHERE user_id = CAST(:uid AS uuid)
    """), {"uid": uid})).fetchone()
    if row is None:
        return None

    meta = jsonify(row.primary_subject_meta)
    wl = jsonify(row.watchlist)

    # Collect every entity_id this row references; one query looks up all redirects.
    ids: list[str] = []
    if row.psid:
        ids.append(row.psid)
    for a in (meta.get("also") or []):
        if isinstance(a, dict) and a.get("id"):
            ids.append(a["id"])
    for x in (wl.get("entity_ids") or []):
        if x:
            ids.append(x)

    remap: dict[str, str] = {}
    if ids:
        rrows = (await db.execute(text("""
            SELECT id::text AS old, redirected_to::text AS new
              FROM entity_dictionary
             WHERE id = ANY(CAST(:ids AS uuid[])) AND redirected_to IS NOT NULL
        """), {"ids": list({i for i in ids if i})})).fetchall()
        remap = {r.old: r.new for r in rrows}

    def _follow(eid: str | None) -> str | None:
        return remap.get(eid, eid) if eid else eid

    # primary_subject_meta — patched id + patched/deduped also[] (immutable build).
    patched_meta: dict[str, Any] = {**meta}
    if meta.get("id"):
        patched_meta["id"] = _follow(meta["id"])
    if meta.get("also"):
        seen: set[str] = set()
        new_also: list[Any] = []
        for a in meta["also"]:
            if isinstance(a, dict) and a.get("id"):
                nid = _follow(a["id"])
                if nid is None or nid in seen:
                    continue
                seen.add(nid)
                new_also.append({**a, "id": nid})
            else:
                new_also.append(a)
        patched_meta["also"] = new_also

    # watchlist — entity_ids resolved + de-duped (immutable build).
    patched_wl: dict[str, Any] = {**wl}
    if wl.get("entity_ids"):
        seen2: set[str] = set()
        new_ids: list[str] = []
        for x in wl["entity_ids"]:
            x2 = _follow(x)
            if x2 and x2 not in seen2:
                seen2.add(x2)
                new_ids.append(x2)
        patched_wl["entity_ids"] = new_ids

    return {
        "primary_subject_id": _follow(row.psid),
        "primary_subject_meta": patched_meta,
        "watchlist": patched_wl,
        "regions": jsonify(row.regions),
        "topics": jsonify(row.topics),
        "languages": jsonify(row.languages),
        "stance": jsonify(row.stance),
        "personality": jsonify(row.personality),
        "events": jsonify(row.events),
        "sources": jsonify(row.sources),
        "delivery": jsonify(row.delivery),
    }
