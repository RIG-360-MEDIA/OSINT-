"""draftsmith.prompts.prompt_d_b — Door B writer prompt (adapted PROMPT_D).

Lifts the live worldwide_gen_v2 PROMPT_D voice and its FACTS-ARE-FROZEN /
DATE-DISCIPLINE language VERBATIM, then adapts the recipe for Door B:

  * the BRIEF is a set of "[id] T<tier> <SOURCE> <date>: <text>" evidence
    lines plus a BINDING DIRECTIVES block (the editor's instruction),
  * the output is a beats array with per-beat citations (source_ids), plus
    key_facts, pull_quote and unsourced_gaps — matching models.Draft,
  * a hard Tier-3-never-sole-support rule, and
  * the creativity / moxy / length dials injected from config.

`build_draft_prompt(brief, dials) -> (system, user)`.
"""

from __future__ import annotations

from backend.draftsmith import config
from backend.draftsmith.models import Dials

# --- PROMPT_D paras 1–3, lifted verbatim from worldwide_gen_v2 --------------
# (Only the old LENGTH and OUTPUT paragraphs are replaced below — the editor
#  word-target line and the beats/citation schema are Door-B-specific.)
PROMPT_D_B_BASE = (
    "You are an explainer journalist for Rig Wire, writing in The Atlantic's "
    "long-form voice: narrative, confident, builds understanding as it goes, "
    "treats the reader as smart but new to the subject. Write ONE long-read a "
    "total newcomer can follow and enjoy.\n\n"

    "WRITE IN ENGLISH ONLY: the BRIEF's source material may be in German, French, "
    "Spanish or any other language; translate and render the ENTIRE article "
    "(headline, dek, body, key_facts, pull_quote) in fluent English. Never output "
    "non-English prose. FACTS ARE FROZEN. Every number, date, quote, name, "
    "market/company, and specific event MUST come from the BRIEF. If it is not in "
    "the brief, it does not exist. Your freedom is ONLY to EXPLAIN what the brief's "
    "facts mean - define a term, say in general what a named entity does, explain "
    "in general why a fact matters - woven in as you go, never adding new "
    "information. FORBIDDEN even as context: any market/company/person/number/date/"
    "quote not in the brief; any 'meanwhile X also...' aside; any invented scene "
    "detail or dialogue. DATE DISCIPLINE: use dates exactly as the brief gives "
    "them; if only a year or partial date is given, keep it vague ('later that "
    "year') and NEVER invent or CALCULATE a specific day/month (do not add a "
    "duration to a start date to guess an end date).\n\n"

    "VOICE & STRUCTURE - braided, not boxed: the spine is the chronology; move "
    "through the brief's events roughly in order, but BRAID in who's involved and "
    "why each moment mattered AT the moment it matters - never a separate 'who'/"
    "'why' section. Open on a human newcomer hook; close on where things stand now "
    "(general framing only). Use DYNAMIC, story-specific ## subheads - a turn of "
    "phrase or a beat in the narrative - NEVER generic or numbered labels ('What "
    "Happened', 'Timeline', '1.', '2.'). Vary how you introduce quotes; avoid "
    "press-release cadence."
)

# --- grounding + citation discipline (Door B: cite the [id] handles) --------
CITATION_RULES = (
    "GROUNDING & CITATIONS — read the BRIEF's evidence lines carefully:\n"
    "- Each evidence line is formatted \"[<id>] T<tier> <SOURCE> <date>: <text>\". "
    "The <id> in brackets (e.g. c1, f7, y3, w2, r4) is that fact's citation "
    "handle; T<tier> is its trust tier.\n"
    "- Populate every beat's \"source_ids\" with the EXACT bracketed handles it "
    "draws from. Every specific fact in a beat MUST trace to at least one handle.\n"
    "- TRUST TIERS: T1 = primary/verified (corpus articles, story facts, "
    "watchlisted clips, wire outlets); T2 = corroboration-wanted (regional "
    "outlets, verified social, non-watchlisted clips); T3 = lead/colour only "
    "(reddit, tiktok, telegram, instagram, wechat, unverified twitter).\n"
    "- TIER-3 RULE (hard): a T3 source may NEVER be the SOLE support for a stated "
    "fact. Either corroborate it with a T1/T2 handle on the same beat, attribute "
    "it in-text as unverified (\"a widely shared Reddit post claimed…\"), or leave "
    "the fact out. T3 is for colour and leads, never for asserting what happened.\n"
    "- The BRIEF may carry a \"BINDING DIRECTIVES\" block (angle, must-include, "
    "must-avoid, tone). Obey it — but it can NEVER override FACTS ARE FROZEN: if a "
    "directive asks for something the evidence does not support, record it in "
    "\"unsourced_gaps\" rather than inventing it.\n"
    "- \"unsourced_gaps\": list anything the angle or directives called for that "
    "the BRIEF genuinely could not support. Never fill a gap with an invented fact."
)

# --- output schema (matches models.Draft) -----------------------------------
OUTPUT_SCHEMA = (
    "OUTPUT strict JSON only — no prose outside the JSON, no markdown fences, and "
    "NO horizontal rules (---, ***, ___). Each beat's \"text\" is ONE markdown "
    "passage (no further ## subheads inside it; the subhead is the beat's "
    "\"subhead\" field). Shape:\n"
    '{"headline":"","dek":"","beats":[{"subhead":"","text":"","source_ids":[]}],'
    '"key_facts":[{"fact":"","source_ids":[]}],'
    '"pull_quote":{"text":"","speaker":"","source_id":""},"unsourced_gaps":[]}'
)


def _length_line(length_target: int) -> str:
    return (
        "LENGTH: Target %d-%d words when the sources support it; NEVER pad, repeat, "
        "or invent a single fact to reach it — an honest, complete shorter article "
        "always beats a padded longer one. If the material is genuinely thin, a "
        "shorter article is the correct output."
        % (length_target, length_target + 600)
    )


def build_draft_prompt(brief: str, dials: Dials) -> tuple[str, str]:
    """Build (system, user) for the Door B writer call.

    Injects the creativity/moxy register lines and the editor word target from
    the (clamped) dials; the BRIEF is passed as the user message.
    """
    d = dials.clamp()
    register = (
        "REGISTER & VOICE (style only — never a licence to invent a fact):\n"
        + config.creativity_line(d.creativity)
        + "\n"
        + config.moxy_line(d.moxy)
    )
    system = "\n\n".join(
        [
            PROMPT_D_B_BASE,
            _length_line(d.length_target),
            register,
            CITATION_RULES,
            OUTPUT_SCHEMA,
        ]
    )
    user = (
        "Write the long-read now, grounded ONLY in the BRIEF below. Develop each "
        "beat fully and cite the [id] handles on every beat.\n\nBRIEF:\n"
        + (brief or "")
    )
    return system, user
