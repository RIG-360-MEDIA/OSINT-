"""Editorial prose for the briefing — clean headlines + detailed paragraphs.

The judge/merge steps give structured facts; this turns the top events into the
polished, multi-sentence copy a media briefing needs (matching the design
mockup's depth). ONLY from the supplied evidence — no fabrication. Uses the
higher-quality model.
"""
from __future__ import annotations

import json
import logging

from groq_client import call_groq

logger = logging.getLogger("briefing.prose")
# llama-3.3-70b: non-reasoning, reliable JSON, fast at batch. gpt-oss-120b is a
# reasoning model that burned its token budget thinking before emitting JSON and
# failed most calls under batch — do not use it here.
PROSE_MODEL = "llama-3.3-70b-versatile"


def _parse(raw: str):
    if not raw:
        return None
    t = raw.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1].rsplit("```", 1)[0]
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(t[i:j + 1])
    except json.JSONDecodeError:
        return None


async def write_event(ev: dict, evidence: list[str]) -> dict:
    """Return {headline, paragraph} for one event, from its evidence sentences."""
    ev_block = "\n".join(f"- {e}" for e in evidence[:8] if e)[:2600]
    net = ev.get("net", 0)
    tone = "critical of the government" if net < -5 else "favourable to the government" if net > 5 else "mixed/neutral"
    sys = (
        "You write ONE item for a government Daily Media Briefing (Telangana I&PR desk). "
        "From the SOURCE SENTENCES only, produce a clean English HEADLINE and a "
        "3-4 sentence PARAGRAPH. The paragraph states plainly: what happened, the "
        "specific government angle (which minister/department/scheme it lands on), "
        "and how the coverage read. Neutral, factual, professional — like a wire "
        "brief. NEVER invent names, numbers, or facts not in the sources. If a fact "
        "isn't in the sources, omit it. No opinions, no advice, no 'the government "
        "should'. Return ONLY JSON: {\"headline\":\"...\",\"paragraph\":\"...\"}"
    )
    user = (f"TOPIC: {ev.get('topic')}   DEPARTMENT: {ev.get('department')}   "
            f"TONE: {tone}   SPREAD: {ev.get('spread_web',0)} web / "
            f"{ev.get('spread_tv',0)} TV / {ev.get('spread_np',0)} newspaper\n"
            f"SOURCE SENTENCES:\n{ev_block}")
    try:
        raw = await call_groq(system=sys, user=user, task_type="brief_generation",
                              model=PROSE_MODEL, json_response=False, max_tokens_override=500)
    except Exception as exc:  # noqa: BLE001
        logger.warning("prose event failed: %s", str(exc)[:120])
        return {}
    p = _parse(raw) or {}
    return {"headline": (p.get("headline") or "").strip(),
            "paragraph": (p.get("paragraph") or "").strip()}


async def write_big_story(big: dict, quotes: list[dict]) -> dict:
    """Return {headline, narrative[]} — a 2-3 paragraph deep narrative."""
    qb = "\n".join(f'- "{q.get("text","")}" ({q.get("source","")})' for q in quotes[:8])[:2800]
    sp = big.get("spread", {})
    sys = (
        "You write THE lead deep-dive for a government Daily Media Briefing. From the "
        "QUOTES/SENTENCES only, produce a clean English HEADLINE and a NARRATIVE of "
        "2-3 short paragraphs: what the story is, what each side said, and where the "
        "government was or was not heard. Neutral, factual, professional. NEVER invent "
        "anything not in the sources. Return ONLY JSON: "
        "{\"headline\":\"...\",\"narrative\":[\"para1\",\"para2\"]}"
    )
    user = (f"SPREAD: {sp.get('web',0)} web / {sp.get('tv',0)} TV / {sp.get('newspaper',0)} "
            f"newspapers, net tone {big.get('net',0)}.\nQUOTES:\n{qb}")
    try:
        raw = await call_groq(system=sys, user=user, task_type="chronicle_generation",
                              model=PROSE_MODEL, json_response=False, max_tokens_override=900)
    except Exception as exc:  # noqa: BLE001
        logger.warning("prose big failed: %s", str(exc)[:120])
        return {}
    p = _parse(raw) or {}
    nar = p.get("narrative")
    if isinstance(nar, str):
        nar = [nar]
    return {"headline": (p.get("headline") or "").strip(),
            "narrative": [str(x).strip() for x in (nar or []) if str(x).strip()]}
