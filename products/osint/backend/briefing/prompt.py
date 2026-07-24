"""The judge prompt — the keystone of the briefing engine.

ONE LLM call per item answers everything at once, because aboutness, tone,
topic, department, scheme and event all need the same single reading of the
text; splitting them lets the answers contradict each other and multiplies cost.

Design goals (per the product goal — "diverse enough to capture everything"):
  * aboutness that judges PORTRAYAL, not mention or mood
  * a closed topic + department vocabulary (no free-text drift)
  * structured event fields so our own merge can group across all three media
  * verbatim evidence so every verdict is verifiable against the source text
  * honest confidence so weak calls fall out rather than guess

The roster + vocabularies are INJECTED (never guessed) so the model always
uses the client-approved definition of "the government".

Output is plain text containing one JSON object; we parse it ourselves (Groq's
strict json_object mode is finicky and returns empty on reasoning models).
"""
from __future__ import annotations

import json
from typing import Any

PROMPT_VERSION = "brief-judge-v1"

# Max body characters sent to the model. Measured 2026-07-24: 6000 covers
# 97-100% of items across all three pillars (web median 1711, TV 1188,
# newspaper 440). Long enough for Eenadu (avg 5530), cheap enough at volume.
BODY_MAX = 6000


def build_system(refdata: dict[str, Any]) -> str:
    """Assemble the system prompt with the org's roster + vocab injected.

    refdata keys:
      org_name, government_names[], opposition_names[], institution_names[],
      topics[], departments[], schemes[] (name only), not_government[] (static)
    """
    gov = "; ".join(refdata["government_names"][:80]) or "(none configured)"
    opp = "; ".join(refdata["opposition_names"][:80]) or "(none configured)"
    inst = "; ".join(refdata["institution_names"][:80]) or "(none configured)"
    topics = " | ".join(refdata["topics"])
    depts = " | ".join(refdata["departments"])
    schemes = " | ".join(refdata["schemes"])

    return f"""You classify ONE news item for a daily MEDIA BRIEFING prepared for the \
{refdata['org_name']} desk. You judge how the item portrays THIS government, and \
extract a few structured facts. You never invent anything.

════════ WHO "THE GOVERNMENT" IS (use ONLY these; do not guess) ════════
GOVERNMENT (ruling side — ministers, allies, the government itself):
  {gov}
OPPOSITION (attacking side):
  {opp}
STATE INSTITUTIONS (government bodies, no party):
  {inst}

These are NOT this government (never treat as the client):
  - The Union/central government, the Prime Minister, central ministers, and
    central agencies (CBI, ED, Income Tax, Election Commission of India)
  - ANY OTHER STATE's government — Andhra Pradesh above all
  - National party leaders acting in a national capacity
  - Sportspeople, film figures, foreign leaders
A COURT is not the government — but a ruling AGAINST the government is still
critical coverage of it (see rules).

════════ QUESTION 1 — IS THIS ITEM ABOUT THE GOVERNMENT? ════════
YES when the item reports on the government's decisions, schemes, spending,
appointments, statements, performance, or on a protest / demand / allegation /
court matter directed at it, OR on conditions it is responsible for (water,
power, roads, hospitals, land, law & order, jobs) where the item ties those
conditions to government action or inaction.
NO when the government is only mentioned in passing: a ceremonial appearance,
a routine crime report with no policy angle, a minister quoted about an
unrelated national matter, or sport / cinema / business with no government angle.
A story about failure with NO name attached (e.g. "no water for ten days in X
village") is still YES if the government is responsible for that service.
A Central decision, fund, sanction or scheme that FLOWS TO, benefits, or is
implemented by THIS state (e.g. "Centre approves extra paddy procurement for
<state>", "Centre sanctions funds for <state>") IS about this government — it
speaks to the state's delivery record and is usually favourable to it. A purely
national item with no channel to this state is NO.

════════ QUESTION 2 — HOW DOES IT PORTRAY THE GOVERNMENT? ════════
  critical    — makes the government look bad: failure, delay, an allegation,
                a protest against it, criticism quoted, a broken promise, an
                adverse court finding, a scandal.
  favourable  — makes it look good: delivery, achievement, an investment won,
                a scheme reaching people, praise quoted, successful action, a
                favourable ruling.
  neutral     — about the government but carries no evaluation: a procedural
                notice, a schedule, a plain factual announcement, or a balanced
                report where neither side dominates.

HARD RULES (these are where naive models fail — follow them exactly):
1. Judge PORTRAYAL, not mood, and not whether the news is sad. A flood, an
   accident or a death is critical ONLY if the item attributes failure to the
   government. The same event with relief underway and no blame is neutral.
2. Criticism reported impartially is STILL critical coverage. If the substance
   of the item is an opposition attack on the government, it is critical even
   though the reporter takes no side.
3. An attack on the CENTRE is not automatically an attack on this state. Judge
   how the ITEM portrays THIS state within the dispute: pressing/resisting/
   winning a demand -> favourable; refused/sidelined/losing funds -> critical;
   no clear standing -> neutral.
4. A court ruling, order or adverse observation AGAINST the government is
   critical. A ruling in its favour is favourable.
5. A government figure praising their own work does NOT by itself make the item
   favourable — judge how the ITEM portrays the government. A press-release
   story run uncritically IS favourable; the same quote inside a scandal story
   is not.
6. Andhra Pradesh is a DIFFERENT state. If the subject is the AP government,
   answer about_government = false.
7. When genuinely unsure, LOWER the confidence rather than guess.

════════ ALSO EXTRACT ════════
strength   — for a critical/favourable verdict: "strong" (front-page-level:
             scandal, major failure/win, wide attack) or "mild". null if neutral.
topic      — EXACTLY ONE of: {topics}
department — the owning department, EXACTLY ONE of: {depts}  (or null if none fits)
scheme     — if a flagship scheme is the subject, EXACTLY ONE of: {schemes}
             (or null). Only if the scheme is genuinely the subject.
event      — the underlying real-world event, so separate reports of the SAME
             event can be grouped:
               action  — short verb phrase ("called a statewide bandh",
                         "barrages held pending expert report")
               actors  — the people/bodies driving it (["NSUI","Left student groups"])
               date    — the event's own date if stated (YYYY-MM-DD) else null
               place   — district/city if stated, else "Telangana"
evidence   — copy EXACTLY ONE sentence from the item, verbatim, in its original
             language (Telugu/Hindi/English), that most supports your verdict. Do
             NOT translate, shorten or paraphrase it. If no single sentence
             supports the verdict, set confidence below 0.5.
lands_on   — the specific minister/department/scheme the coverage lands on, or null.
confidence — 0.0 to 1.0, honest.

════════ OUTPUT ════════
Return ONE JSON object and NOTHING else — no preamble, no code fence:
{{"about_government": true|false, "verdict": "critical"|"favourable"|"neutral",
"strength": "strong"|"mild"|null, "topic": "<one of the list>", "department":
"<one or null>", "scheme": "<one or null>", "event": {{"action": "<phrase>",
"actors": ["..."], "date": "YYYY-MM-DD"|null, "place": "<place>"}}, "evidence":
"<one verbatim sentence>", "lands_on": "<text or null>", "confidence": 0.0}}"""


def build_user(item: dict[str, Any]) -> str:
    """item: {source, medium, published_at, title, body, lang}"""
    body = (item.get("body") or "").strip()
    if len(body) > BODY_MAX:
        body = body[:BODY_MAX]
    return (
        f"OUTLET: {item.get('source','?')}   MEDIUM: {item.get('medium','?')}   "
        f"LANGUAGE: {item.get('lang','?')}\n"
        f"DATE: {item.get('published_at','?')}\n"
        f"HEADLINE: {item.get('title','')}\n"
        f"BODY:\n{body}"
    )


def parse_verdict(raw: str) -> dict[str, Any] | None:
    """Extract the JSON object from the model's reply. Returns None if unparseable."""
    if not raw:
        return None
    txt = raw.strip()
    # strip code fences if present
    if txt.startswith("```"):
        txt = txt.split("\n", 1)[-1].rsplit("```", 1)[0]
    i, j = txt.find("{"), txt.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(txt[i:j + 1])
    except json.JSONDecodeError:
        return None
