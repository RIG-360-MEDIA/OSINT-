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
    """Return the user's brief prefs, or None if they have none saved."""
    row = (await db.execute(text("""
        SELECT primary_subject_id::text AS psid, primary_subject_meta,
               watchlist, regions, topics
          FROM analytics.user_brief_prefs WHERE user_id = CAST(:uid AS uuid)
    """), {"uid": uid})).fetchone()
    if row is None:
        return None
    return {
        "primary_subject_id": row.psid,
        "primary_subject_meta": jsonify(row.primary_subject_meta),
        "watchlist": jsonify(row.watchlist),
        "regions": jsonify(row.regions),
        "topics": jsonify(row.topics),
    }
