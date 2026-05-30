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
import re
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

    # Left "digest" — the ACTUAL top news, grouped by the entity it is about,
    # subject-first. This is the real "what's moving on your watch" content
    # (not a meta count). Each entity shows its lead development + how many.
    # Resolve a matched entity name to a WATCHLIST entity by shared distinctive
    # token (generic words like 'congress'/'reddy' excluded so a stray "Trinamool
    # Congress" tag doesn't masquerade as your INC, and "Kalvakuntla Kavitha"
    # resolves to "K. Kavitha"). Unresolved = not on your watch → skipped.
    _STOP = {"congress", "party", "india", "indian", "national", "bharat", "janata",
             "samithi", "desam", "telugu", "majlis", "reddy", "rao", "kumar", "singh",
             "chief", "minister", "government", "govt"}

    def _toks(s: str | None) -> set[str]:
        return {t for t in re.split(r"[^a-z]+", (s or "").lower()) if len(t) >= 4 and t not in _STOP}

    _wl_tok = [(mm.get("name"), mm.get("camp"), _toks(mm.get("name"))) for mm in meta if mm.get("name")]

    def _resolve(matched: str | None) -> tuple[str | None, str | None]:
        mt = _toks(matched)
        for nm, camp, toks in _wl_tok:
            if toks & mt:
                return nm, camp
        return None, None

    groups: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for r in scored:                       # scored is already sorted by score desc
        name, camp = _resolve(r.get("matched"))
        if name is None:                   # not a watchlist entity → skip noise
            continue
        if name not in groups:
            groups[name] = {"entity": name, "camp": camp, "items": []}
            order.append(name)
        groups[name]["items"].append(r)

    subj_l = subj_name.lower()
    ranked = sorted(
        (groups[k] for k in order),
        key=lambda g: (0 if subj_l in g["entity"].lower() else 1, -g["items"][0]["score"]),
    )
    digest = [{
        "entity": g["entity"], "camp": g["camp"],
        "headline": (g["items"][0]["title"] or "").strip(),
        "outlets": g["items"][0]["source"],
        "count": len(g["items"]),
    } for g in ranked[:6]]

    n = len(subject_items)
    posture = (f"{subj_name} leads coverage" if n else f"{subj_name} is quiet today")
    if opp_items:
        posture += f" · opposition active on {len(opp_items)} front{'s' if len(opp_items) != 1 else ''}"

    return {
        "as_of": as_of,
        "personalized": True,
        "subject": subj_name,
        "coverage_count": n,
        "posture": posture,
        "digest": digest,
        "needs_attention": attention,
    }
