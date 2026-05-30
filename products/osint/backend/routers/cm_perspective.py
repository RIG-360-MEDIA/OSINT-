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
from llm_synth import synthesize_dossier, synthesize_paragraph
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
    window_hours: int = Query(default=96, ge=6, le=168),
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

    # Flowing prose summary of the interval's events — grounded (built from real
    # headlines), grouped govt / opposition / governance, connected with
    # transitions, for the user to READ. Templated for now; swap to an LLM
    # synthesis over these same facts (faithfulness-gated) once a key is wired.
    def _clean(h: str | None) -> str:
        return (h or "").split("|")[0].strip().rstrip(" .,-")

    def _norm(h: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", (h or "").lower()).strip()

    def _good(h: str) -> bool:
        # Drop degenerate headlines: a bare name / fragment with no clause reads
        # as broken prose ("KCR — Harish Rao."). Require a real multi-word line.
        return len(h) >= 24 and len(h.split()) >= 4

    def _join(xs: list[str]) -> str:
        xs = [x for x in xs if x]
        if len(xs) <= 1:
            return xs[0] if xs else ""
        return "; ".join(xs[:-1]) + "; and " + xs[-1]

    # One headline is used once, across all three groups (no repeats).
    _used: set[str] = set()

    def _take(title: str | None) -> str | None:
        c = _clean(title)
        if not _good(c):
            return None
        k = _norm(c)
        if k in _used:
            return None
        _used.add(k)
        return c

    subj_lines: list[str] = []
    for r in subject_items:
        c = _take(r["title"])
        if c:
            subj_lines.append(c)
        if len(subj_lines) >= 2:
            break

    opp_devs: list[str] = []
    opp_fronts: set[str] = set()
    for r in opp_items:
        c = _take(r["title"])
        if not c:
            continue
        nm, _c = _resolve(r.get("matched"))
        if nm:
            opp_fronts.add(nm)
        opp_devs.append(f"{nm or 'the opposition'} — {c}")
        if len(opp_devs) >= 3:
            break

    govt_other: list[str] = []
    for r in scored:
        _nm, camp = _resolve(r.get("matched"))
        if camp != "govt" or r["ent_tier"] < 2:
            continue
        c = _take(r["title"])
        if c:
            govt_other.append(c)
        if len(govt_other) >= 2:
            break

    parts: list[str] = []
    if subj_lines:
        parts.append(f"Over the last {window_hours} hours, coverage centres on {subj_name} — "
                     + _join(subj_lines) + ".")
    if opp_devs:
        n_fronts = len(opp_fronts) or len(opp_devs)
        lead = (f"The opposition is active on {n_fronts} fronts — " if n_fronts > 1
                else "The opposition is active — ")
        parts.append(lead + _join(opp_devs) + ".")
    if govt_other:
        parts.append("On the governance front, " + _join(govt_other) + ".")
    summary = " ".join(parts) if parts else f"Little has centred on {subj_name} in this window."

    # LLM synthesis over the SAME real, de-duped headlines — a smoother flowing
    # paragraph than the template can produce. Grounded + faithfulness-gated
    # inside synthesize_paragraph; on any failure (no keys, timeout, unsupported
    # number) it returns None and we keep the deterministic template above.
    summary_source = "template"
    fact_lines: list[str] = []
    if subj_lines:
        fact_lines.append(f"PRINCIPAL ({subj_name}) — own actions / direct coverage:")
        fact_lines += [f"  - {h}" for h in subj_lines]
    if opp_devs:
        fact_lines.append("OPPOSITION pressure (figure — what they said or did):")
        fact_lines += [f"  - {d}" for d in opp_devs]
    if govt_other:
        fact_lines.append("GOVERNANCE / administration:")
        fact_lines += [f"  - {h}" for h in govt_other]
    facts = "\n".join(fact_lines)
    if facts:
        system = (
            "/no_think\n"
            f"You are an intelligence editor briefing the office of {subj_name}. "
            "Write ONE tight, flowing paragraph (about 90-130 words) that "
            "synthesises the developments below into a readable narrative for a "
            "busy principal. Rules: use ONLY the facts given; do NOT invent "
            "numbers, names, places, parties, or outcomes; do NOT add analysis, "
            "opinion, or recommendations; move naturally from the principal's own "
            "actions to opposition pressure to governance items, connecting with "
            "transitions. No bullet points, no headings, no preamble, no closing "
            "line — output only the paragraph."
        )
        llm = await synthesize_paragraph(system=system, facts=facts, source_check=facts)
        if llm:
            summary = llm
            summary_source = "llm"

    # ── Narrative balance (real) + deep strategic analysis (LLM, grounded). ───
    # By COVERAGE VOLUME, not the sparse stance table: of the watched coverage,
    # how much is opposition-driven vs principal/government-driven.
    govt_cov = sum(1 for r in scored if r["ent_tier"] == 3 or _resolve(r.get("matched"))[1] == "govt")
    opp_cov = len(opp_items)
    _bt = govt_cov + opp_cov
    narrative_balance = {
        "attack": opp_cov,
        "govt": govt_cov,
        "total": _bt,
        "attack_pct": round(100 * opp_cov / _bt) if _bt else 0,
        "govt_pct": round(100 * govt_cov / _bt) if _bt else 0,
    }
    opposition_fronts = sorted(opp_fronts)

    # The summary above is "what happened"; this is the analyst's "what it means
    # + what to do" — a deeper strategic read over the same real facts.
    deep_analysis = None
    if facts:
        da_facts = facts
        if _bt:
            da_facts += (f"\nNARRATIVE BALANCE (of stance-coded coverage on the watch): "
                         f"{narrative_balance['attack_pct']}% opposition attack vs "
                         f"{narrative_balance['govt_pct']}% government messaging.")
        if opposition_fronts:
            da_facts += "\nOPPOSITION FIGURES ACTIVE: " + ", ".join(opposition_fronts)
        # Thin-sample guard: when opposition signal is sparse, the analyst must
        # hedge to "this window" rather than declare a durable narrative monopoly.
        _thin = (not opposition_fronts) or (_bt < 8)
        _hedge = (" NOTE: opposition signal in THIS window is limited — if pressure is "
                  "low, say so plainly as 'limited opposition signal in this window' and "
                  "do NOT over-claim a durable 'narrative monopoly' or permanent dominance; "
                  "scope any such read to the current window only." if _thin else "")
        da_system = (
            "/no_think\n"
            f"You are a senior political-intelligence analyst briefing the office of {subj_name}. "
            "Using ONLY the facts below, write a SHORT but deep strategic assessment (3-5 sentences): "
            "the principal's standing right now, the main pressure or threat, who is setting the "
            "narrative (the principal or the opposition), and the near-term outlook. Then give 2-3 "
            "concrete recommended actions. Be analytical and decision-useful; describe momentum and "
            "posture QUALITATIVELY and do NOT cite specific numbers or invent names, dates, or "
            "outcomes." + _hedge +
            "\nFormat EXACTLY:\nASSESSMENT: <3-5 sentences>\nACTIONS:\n- <action>\n- <action>"
        )
        deep_analysis = await synthesize_dossier(system=da_system, facts=da_facts, source_check=da_facts)

    return {
        "as_of": as_of,
        "personalized": True,
        "subject": subj_name,
        "coverage_count": n,
        "posture": posture,
        "summary": summary,
        "summary_source": summary_source,
        "digest": digest,
        "narrative_balance": narrative_balance,
        "opposition_fronts": opposition_fronts,
        "deep_analysis": deep_analysis,
        "needs_attention": attention,
    }
