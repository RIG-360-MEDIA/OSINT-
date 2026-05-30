"""GET /api/brief/cm_perspective — Block 2: how the principal is being covered.

Left  : a written read of the subject's coverage (prominence + lead story).
Right : "Needs Your Attention" — the items demanding a response: opposition
        attacks (a watchlist figure in the 'opposition' camp driving the story)
        + high-severity coverage about the principal. Source-linked, real.

Built on the same relevance core (relevance.py): persona-agnostic — a Delhi
CP or a PR lead gets their own principal + their own opposition, same engine.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from auth.middleware import get_optional_user
from db import get_db
from relevance import score_relevant

router = APIRouter(prefix="/api/brief", tags=["brief"])

CRIT_DOMAINS = {"SECURITY", "LEGAL"}
DOT = {"critical": "🔴", "high": "🟠", "moderate": "🟡", "low": "⚪"}


def _jsonify(v: Any) -> dict:
    if v is None:
        return {}
    return v if isinstance(v, dict) else json.loads(v)


def _severity(ent_tier: int, topic: str | None) -> str:
    crit = topic in CRIT_DOMAINS
    if ent_tier >= 2 and crit:
        return "critical"
    if ent_tier >= 3 or crit:
        return "high"
    if ent_tier >= 2:
        return "moderate"
    return "low"


def _is_opp(matched: str | None, opp: set[str]) -> bool:
    m = (matched or "").lower()
    if not m:
        return False
    return any(o and (o in m or m in o) for o in opp)


async def _load_prefs(db, uid: str) -> dict[str, Any] | None:
    row = (await db.execute(text("""
        SELECT primary_subject_id::text AS psid, primary_subject_meta,
               watchlist, regions, topics
          FROM analytics.user_brief_prefs WHERE user_id = CAST(:uid AS uuid)
    """), {"uid": uid})).fetchone()
    if row is None:
        return None
    return {
        "primary_subject_id": row.psid,
        "primary_subject_meta": _jsonify(row.primary_subject_meta),
        "watchlist": _jsonify(row.watchlist),
        "regions": _jsonify(row.regions),
        "topics": _jsonify(row.topics),
    }


@router.get("/cm_perspective")
async def cm_perspective(
    window_hours: int = Query(default=48, ge=6, le=168),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    async with get_db() as db:
        as_of = (await db.execute(text(
            "SELECT to_char(analytics.now_sim(), 'YYYY-MM-DD\"T\"HH24:MI:SS')"
        ))).scalar()

        prefs = await _load_prefs(db, user["id"]) if user else None
        if not prefs:
            return {"as_of": as_of, "personalized": False,
                    "subject": None, "read": "Sign in to see your principal's coverage.",
                    "coverage_count": 0, "needs_attention": []}

        scored = await score_relevant(db, prefs, window_hours=window_hours, limit=60)

    subj_name = (prefs.get("primary_subject_meta") or {}).get("name") or "your principal"
    meta = (prefs.get("watchlist") or {}).get("entity_meta") or []
    opp = {(m.get("name") or "").lower() for m in meta if m.get("camp") == "opposition"}

    # Stories centred on the principal (subject tier).
    subject_items = [r for r in scored if r["ent_tier"] == 3]
    # Opposition-driven stories (a watchlist opposition figure is the matched entity).
    opp_items = [r for r in scored if _is_opp(r.get("matched"), opp)]

    # "Needs Your Attention" = things to RESPOND to, not good news. Opposition
    # attacks (reliable signal) + coverage about the principal in a risk domain
    # (security / legal). A positive govt announcement belongs in the read, not
    # the alert panel — so we deliberately exclude plain subject coverage.
    pool = opp_items + [r for r in subject_items if (r["topic"] in CRIT_DOMAINS)]
    seen: set[str] = set()
    attention = []
    for r in sorted(pool, key=lambda x: x["score"], reverse=True):
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        sev = "high" if _is_opp(r.get("matched"), opp) else _severity(r["ent_tier"], r["topic"])
        attention.append({
            "severity": sev, "dot": DOT[sev],
            "kind": "opposition" if _is_opp(r.get("matched"), opp) else "coverage",
            "headline": (r["title"] or "").strip(),
            "matched": r["matched"],
            "outlets": r["source"],
            "cluster_id": r["id"],
        })
        if len(attention) >= 3:
            break

    # Left read — prominence + lead story (real; degrades gracefully).
    n = len(subject_items)
    lead = subject_items[0]["title"].strip() if subject_items else None
    if n == 0:
        read = f"{subj_name} is quiet in coverage right now — nothing centred on them in this window."
    else:
        read = f"{n} development{'s' if n != 1 else ''} centre on {subj_name} right now."
        if lead:
            read += f" Leading: “{lead}”."
        if opp_items:
            read += f" The opposition is active — {len(opp_items)} stories driven by your rivals."

    return {
        "as_of": as_of,
        "personalized": True,
        "subject": subj_name,
        "coverage_count": n,
        "read": read,
        "needs_attention": attention,
    }
