"""Editorial prose for the briefing — clean headlines + detailed paragraphs.

The judge/merge steps give structured facts; this turns the top events into the
polished, multi-sentence copy a media briefing needs (matching the design
mockup's depth). ONLY from the supplied evidence — no fabrication. Uses the
higher-quality model.
"""
from __future__ import annotations

import json
import logging
import re

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
    i = t.find("{")
    if i < 0:
        return None
    j = t.rfind("}")
    if j > i:
        try:
            return json.loads(t[i:j + 1])
        except json.JSONDecodeError:
            pass
    # salvage a truncated object (model hit the token cap mid-JSON): keep only
    # whole "key": "value" string pairs and whole string-array fields, then close.
    body = t[i + 1:]
    pairs = re.findall(r'"(\w+)"\s*:\s*"((?:[^"\\]|\\.)*)"', body)
    arrays = re.findall(r'"(\w+)"\s*:\s*\[((?:\s*"(?:[^"\\]|\\.)*"\s*,?)+)\s*\]', body)
    obj: dict = {}
    for k, v in pairs:
        obj.setdefault(k, v)
    for k, inner in arrays:
        try:
            obj[k] = json.loads("[" + inner + "]")
        except json.JSONDecodeError:
            pass
    return obj or None


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


def _spread_words(sp: dict) -> str:
    return (f"{sp.get('web',0)} online outlets, {sp.get('tv',0)} television channels "
            f"and {sp.get('newspaper',0)} newspapers")


async def write_big_story(big: dict, beats: list[dict]) -> dict:
    """Return the full lead package for §2 — mockup-depth.

    {headline, standfirst, narrative[], timeline[{when,medium,text}], silence, angle}

    `beats` are the story's own evidence sentences, each tagged with a coarse
    time-of-day bucket and pillar, sorted through the day — the raw material the
    model condenses (STRICTLY, no invention) into the narrative + timeline.
    """
    bl = "\n".join(
        f"- [{b.get('when','')}/{b.get('pillar','')}/{b.get('verdict','')}] "
        f"\"{(b.get('text') or '')[:200]}\" ({b.get('source','')})"
        for b in beats[:16])[:4200]
    sp = big.get("spread", {})
    dom = big.get("dominant_pillar", "")  # pillar that carried the most reports
    sys = (
        "You are the senior editor writing THE lead deep-dive for a government Daily "
        "Media Briefing (Telangana I&PR desk). You are given the day's SOURCE LINES for "
        "the single most-covered story, each tagged [time-of-day / medium / tone] in "
        "time order. Write STRICTLY from these lines — never invent a name, number, "
        "quote, event or time. If something isn't in the lines, leave it out.\n"
        "Produce JSON with these fields:\n"
        "  headline  : clean English headline, specific, no jargon.\n"
        "  standfirst: 2-3 sentences. Name the subject, state the spread in words, say "
        "how it read overall, and which medium drove it. Like the bold lead of a wire.\n"
        "  narrative : EXACTLY 3-4 separate paragraphs (a JSON array of 3-4 "
        "strings, each 2-4 sentences) — do NOT return one long paragraph. "
        "Paragraph 1: what happened and the government's position. Paragraph 2: the "
        "opposition's line / the criticism. Paragraph 3: where the two arguments met "
        "or missed, and how the coverage split by medium. Add a 4th only if the "
        "sources support it. Factual, neutral, specific.\n"
        "  timeline  : 3-5 beats of how coverage moved through the day, each "
        "{when:'Morning'|'Midday'|'Evening'|'Late evening'|'Next morning', "
        "medium:'Web'|'TV'|'Web + TV'|'Print', text:'one sentence, <=16 words'}.\n"
        "  silence   : if a specific opposition claim went unanswered by any government "
        "figure in the coverage, one sentence naming it; else ''.\n"
        "  angle     : one sentence on how the framing differed by medium (TV vs online "
        "vs print), only if the lines support it; else ''.\n"
        "Return ONLY the JSON object."
    )
    user = (f"SPREAD: {_spread_words(sp)}. NET TONE {big.get('net',0)}. "
            f"MOST REPORTS CAME FROM: {dom or 'n/a'}.\nSOURCE LINES (time-ordered):\n{bl}")
    try:
        raw = await call_groq(system=sys, user=user, task_type="chronicle_generation",
                              model=PROSE_MODEL, json_response=False, max_tokens_override=3200)
    except Exception as exc:  # noqa: BLE001
        logger.warning("prose big failed: %s", str(exc)[:120])
        return {}
    p = _parse(raw) or {}
    nar = p.get("narrative")
    if isinstance(nar, str):
        nar = [nar]
    tl = []
    for t in (p.get("timeline") or []):
        if isinstance(t, dict) and (t.get("text") or "").strip():
            tl.append({"when": str(t.get("when", "")).strip(),
                       "medium": str(t.get("medium", "")).strip(),
                       "text": str(t.get("text", "")).strip()})
    return {"headline": (p.get("headline") or "").strip(),
            "standfirst": (p.get("standfirst") or "").strip(),
            "narrative": [str(x).strip() for x in (nar or []) if str(x).strip()],
            "timeline": tl[:5],
            "silence": (p.get("silence") or "").strip(),
            "angle": (p.get("angle") or "").strip()}
