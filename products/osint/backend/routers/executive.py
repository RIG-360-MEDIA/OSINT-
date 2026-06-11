"""GET /api/brief/executive — Block 1: The Executive Read (situation top-fold).

Sourced from the generic relevance core (relevance.py): the user's own
relevant article stream — watchlist (tiered, alias-expanded) + regions +
keywords, salience-gated and noise-demoted — NOT the global cluster pool.
So a Telangana CM sees Telangana; a Delhi user sees Delhi; same engine.

Findings carry a real headline + real `summary_executive` and the matched
entity ("why it's here"). Severity is deterministic.
"""
from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from auth.middleware import get_optional_user
from db import get_db
from llm_synth import synthesize_paragraph
from relevance import score_relevant

router = APIRouter(prefix="/api/brief", tags=["brief"])

CRIT_DOMAINS = {"SECURITY", "LEGAL"}
DOT = {"critical": "🔴", "high": "🟠", "moderate": "🟡", "low": "⚪"}


def _norm(t: str | None) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (t or "").lower()).strip()[:60]


def _severity(ent_tier: int, topic: str | None) -> str:
    crit = topic in CRIT_DOMAINS
    if ent_tier >= 2 and crit:
        return "critical"
    if ent_tier >= 3 or crit:
        return "high"
    if ent_tier >= 2:
        return "moderate"
    return "low"


def _jsonify(v: Any) -> dict:
    if v is None:
        return {}
    return v if isinstance(v, dict) else json.loads(v)


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


@router.get("/executive")
async def get_executive(
    window_hours: int = Query(default=48, ge=6, le=168),
    limit: int = Query(default=7, ge=3, le=12),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    async with get_db() as db:
        as_of = (await db.execute(text(
            "SELECT to_char(analytics.now_sim(), 'YYYY-MM-DD\"T\"HH24:MI:SS')"
        ))).scalar()

        prefs = await _load_prefs(db, user["id"]) if user else None
        if not prefs:
            return {
                "as_of": as_of, "window_hours": window_hours, "personalized": False,
                "bluf": "Sign in to see your personalised brief.", "findings": [],
            }

        scored = await score_relevant(db, prefs, window_hours=window_hours, limit=50)

    # Dedupe near-identical re-scrapes by normalised title; keep highest-scored.
    # Apply a relevance FLOOR — better to show 4 sharp developments than to pad
    # the brief with demoted passing-mention fillers (e.g. a Modi op-ed that
    # merely carries a stray Telangana tag).
    MIN_SCORE = 1.2
    seen: set[str] = set()
    devs: list[dict[str, Any]] = []
    for r in scored:
        if r["score"] < MIN_SCORE:
            continue
        k = _norm(r["title"])
        if not k or k in seen:
            continue
        seen.add(k)
        devs.append(r)

    top = devs[:limit]
    findings = []
    for r in top:
        sev = _severity(r["ent_tier"], r["topic"])
        findings.append({
            "severity": sev,
            "dot": DOT[sev],
            "headline": (r["title"] or "").strip(),
            "context": (r["summary"] or "").strip()[:240],
            "matched": r["matched"],          # the "why it's here" trust line
            "topic": r["topic"],
            "outlets": r["source"],
            "sources": 1,
            "score": r["score"],
            "cluster_id": r["id"],
        })

    # Deterministic BLUF — always computed; the guaranteed fallback.
    need = sum(1 for f in findings if f["severity"] in ("critical", "high"))
    if not findings:
        bluf = "Quiet window — nothing on your watch crossed the threshold."
    elif need == 0:
        bluf = f"{len(findings)} developments on your watch; nothing flagged for immediate attention."
    else:
        bluf = f"{len(findings)} developments on your watch · {need} need attention."
    bluf_source = "template"

    # LLM upgrade: a real bottom-line-up-front synthesised from the top findings
    # (grounded + numeric-faithfulness-gated in llm_synth). Falls back to the
    # deterministic count line on any failure (no keys, timeout, number drift).
    if findings:
        subj = (prefs.get("primary_subject_meta") or {}).get("name") or "the principal"
        fact_lines = [
            f"- [{f['severity']}] {f['headline']}"
            + (f" (re: {f['matched']})" if f.get("matched") else "")
            for f in findings[:6]
        ]
        facts = (
            f"PRINCIPAL: {subj}\n"
            f"WINDOW: last {window_hours} hours\n"
            f"TOTALS: {len(findings)} developments in scope, {need} marked high-priority.\n"
            "TOP DEVELOPMENTS ON THEIR WATCH (most important first):\n"
            + "\n".join(fact_lines)
        )
        system = (
            "/no_think\n"
            f"You are an intelligence editor writing the bottom-line-up-front for "
            f"{subj}'s morning brief. In ONE or TWO crisp sentences (max ~35 words), "
            "state the single most important thing on their watch right now and the "
            "overall posture. Use ONLY the developments listed; do NOT invent numbers, "
            "names, places, or outcomes. No preamble, no list, no label — output only "
            "the sentence(s)."
        )
        llm = await synthesize_paragraph(
            system=system, facts=facts, source_check=facts,
            min_words=6, min_chars=25,
        )
        if llm:
            bluf = llm
            bluf_source = "llm"

    return {
        "as_of": as_of,
        "window_hours": window_hours,
        "personalized": True,
        "bluf": bluf,
        "bluf_source": bluf_source,
        "findings": findings,
    }
