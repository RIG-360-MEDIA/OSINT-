"""Agentic layer (Category-5): smart-filter, a grounded coverage Q&A agent, and
the data-as-tools registry that an MCP server exposes.

Generic + grounded. The Q&A agent answers ONLY from retrieved facts (faithfulness
via llm_synth); the smart-filter is LLM-free (pure relevance core). The same tool
functions back both the HTTP endpoints and the MCP server (mcp_server.py).
"""
from __future__ import annotations

from typing import Any

from llm_synth import synthesize_paragraph
from posture import compute_posture
from relevance import score_relevant


async def smart_filter(db, prefs: dict[str, Any], window_hours: int = 96,
                       limit: int = 10) -> dict[str, Any]:
    """Overload-killer: 500 articles/day -> a ranked, reasoned top-N. LLM-free."""
    scored = await score_relevant(db, prefs, window_hours=window_hours, limit=limit)
    items = []
    for r in scored:
        why = []
        if r.get("tc"):
            why.append("in headline")
        if r.get("ent_tier", 0) >= 3:
            why.append("about your principal")
        elif r.get("ent_tier", 0) == 2:
            why.append("core watchlist")
        if r.get("geo_hit"):
            why.append("your region")
        items.append({"id": r["id"], "title": r["title"], "source": r["source"],
                      "score": r["score"], "matched": r.get("matched"),
                      "why": ", ".join(why) or "relevant"})
    return {"items": items, "n": len(items)}


async def tool_posture(db, prefs: dict[str, Any], window_hours: int = 504) -> dict[str, Any]:
    """MCP tool: compact posture snapshot for an agent to reason over."""
    p = await compute_posture(db, prefs, window_hours)
    if not p.get("personalized"):
        return {"personalized": False}
    m = p["metrics"]
    return {
        "subject": p["subject"],
        "pressure": m["weighted_pressure"]["pressure"],
        "share_of_voice_pct": m["share_of_voice"].get("principal_sov_pct"),
        "trend": m["stance_trajectory"].get("direction"),
        "most_hostile": [o["outlet"] for o in m["friend_foe_fence"]["hostile"][:3]],
        "opposition_heat": [{"name": t["name"], "heat": t["heat"]} for t in m["target_heat"]["items"][:3]],
        "cross_language_gap": m["cross_language_gap"].get("gap"),
    }


async def cm_coverage_agent(db, prefs: dict[str, Any], question: str,
                            window_hours: int = 504) -> dict[str, Any]:
    """'How is my CM covered this week?' — grounded answer over posture + top stories."""
    snap = await tool_posture(db, prefs, window_hours)
    if not snap.get("subject"):
        return {"answer": None, "grounded": False, "reason": "no principal"}
    scored = await score_relevant(db, prefs, window_hours=min(window_hours, 168), limit=8)
    facts = (f"SUBJECT: {snap['subject']}\nPRESSURE: {snap['pressure']}\n"
             f"SHARE OF VOICE: {snap['share_of_voice_pct']}%\nTREND: {snap['trend']}\n"
             f"MOST HOSTILE OUTLETS: {', '.join(snap['most_hostile'])}\n"
             f"CROSS-LANGUAGE GAP: {snap['cross_language_gap']}\n"
             "TOP STORIES:\n" + "\n".join(f"- {r['title']} ({r['source']})" for r in scored))
    try:
        ans = await synthesize_paragraph(
            system=f"/no_think Answer this question about {snap['subject']}'s coverage in English, "
                   f"using ONLY the facts below. Be specific and grounded. Question: {question}",
            facts=facts, source_check=facts, min_words=8, min_chars=30)
    except Exception as e:  # noqa: BLE001
        return {"answer": None, "grounded": False, "error": str(e)[:80], "facts_used": facts}
    return {"answer": ans, "grounded": bool(ans), "snapshot": snap}


# Registry consumed by both the HTTP router and the MCP server.
MCP_TOOLS = {
    "rig_posture_snapshot": ("Posture snapshot (pressure, hostility, opposition heat) for the user's principal.", tool_posture),
    "rig_smart_filter": ("Ranked, de-noised top stories for the user (overload-killer).", smart_filter),
    "rig_coverage_qa": ("Answer a natural-language question about the principal's coverage, grounded in the data.", cm_coverage_agent),
}
