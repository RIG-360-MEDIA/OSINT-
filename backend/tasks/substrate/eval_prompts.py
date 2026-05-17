"""
JSON-extraction prompt evaluation harness.

Self-contained — does NOT touch run_corpus_pass.py production logic.

Selects a 200-article stratified sample, runs 6 prompt variants (baseline +
A..E) through Cerebras `qwen-3-235b-a22b-instruct-2507`, captures
quality/latency metrics, writes raw outputs to /tmp/eval_raw.jsonl and a
summary table to /tmp/eval_summary.txt.

Run inside the rig-backend container:

    docker exec rig-backend python3 -u -m backend.tasks.substrate.eval_prompts

The script saves partial progress to /tmp/eval_raw.jsonl every 50 completions
so a crash mid-run does not lose results.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import asyncpg

from backend.nlp.groq_client import (
    GroqCallFailed,
    GroqQuotaExhausted,
    _call_cerebras,
)
from backend.tasks.substrate.run_corpus_pass import (
    GROQ_SYS,
    GROQ_SYS_NON_ENGLISH,
    INDIC_LANGS,
    MAX_BODY_FOR_GROQ_ENGLISH,
    MAX_BODY_FOR_GROQ_INDIC,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("eval_prompts")


# ─────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────

EVAL_MODEL = "qwen-3-235b-a22b-instruct-2507"   # Cerebras uniform model
EVAL_TASK_TYPE = "profile_extraction"
CONCURRENCY = 8
SAMPLE_SIZE_TARGET = 200
PARTIAL_FLUSH_EVERY = 50

OUTPUT_RAW = Path("/tmp/eval_raw.jsonl")
OUTPUT_SUMMARY = Path("/tmp/eval_summary.txt")
SAMPLE_IDS_PATH = Path("/tmp/eval_sample_ids.txt")

META_INTRO_PHRASES = (
    "the article", "this article", "it is about",
    "it discusses", "this is",
)


# ─────────────────────────────────────────────────────────────────────
# PROMPT VARIANTS
# ─────────────────────────────────────────────────────────────────────

# Snippet to delete from baseline → A onwards: the "empty/junk default" line
# encourages the LLM to fall back to neutral/factual on borderline-empty
# bodies and inflates the factual rate.
EMPTY_JUNK_LINE = (
    "- If article is empty/junk: article_type=other, all arrays empty, "
    "register defaults to neutral/factual.\n"
)

PROMPT_BASELINE = GROQ_SYS

# Definitions appended at the end of variant A. Per-enum descriptions force
# the model to actively choose rather than fall back to default category.
_TYPE_DEFS = """
ARTICLE_TYPE DEFINITIONS (pick the most specific match — NEVER default to 'news' if a better fit exists):
- news: hard reportage on an event that just happened, neutral attribution
- opinion: signed editorial / column / op-ed advocating a position
- analysis: explanatory piece weighing multiple factors; usually labelled 'analysis'
- explainer: 'what is X / why does X matter' format, evergreen background
- listicle: numbered list of items ('5 reasons', 'Top 10 …')
- horoscope: zodiac predictions
- recipe: cooking instructions with ingredients + steps
- live_blog: timestamped rolling updates on one event
- photo_essay: gallery/slideshow with captions as the body
- interview: Q&A transcript of a single subject
- press_release: corporate / govt PR copy verbatim (no journalistic framing)
- sports_result: scoreline + match report
- other: none of the above (use sparingly)

REGISTER.RHETORICAL_STYLE DEFINITIONS:
- factual: descriptive only, no value-loaded language
- analytical: weighs multiple factors, uses "however"/"on the other hand"/"by contrast"
- polemical: uses charged terms ("shameful", "must", "failure", "betrayal"); argumentative
- sympathetic: humanises subject; emotion-forward framing of suffering or struggle
- mocking: derisive tone, sarcasm, ridicule of named actors
- promotional: praises subject without counterpoints; PR/advertorial register
- sensational: lurid framing, emotional adjectives ("shocking", "horrifying", "stunning")
"""

PROMPT_A = (GROQ_SYS.replace(EMPTY_JUNK_LINE, "")) + _TYPE_DEFS

_NEGATION_RULES = """
NEGATION RULES (hard constraints — violating these is a parse error):
- primary_subject MUST NOT start with "The article", "This article", "It is about",
  "It discusses", or "This is". Write it as a noun phrase describing the underlying
  event/subject. Example WRONG: "The article discusses Telangana's new policy."
  Example RIGHT: "Telangana cabinet clears new EV-subsidy framework."
- primary_subject MUST NOT be a verbatim copy of the title.
- numbers[].unit MUST be canonical text — write "percent" not "%", "year" not "years",
  "rupees" not "Rs"/"₹", "crore" not "Cr", "kilometre" not "km", "lakh" not "L".
- quotes[].is_verbatim is true ONLY if the text appears between actual quotation marks
  in the body. Paraphrases — even close paraphrases — are is_verbatim=false.
- actor_stances[].intensity must AVOID the [0.45, 0.55] band entirely. Either commit to
  weak (≤0.4), clear (0.6-0.8), or maximal (≥0.9). 0.5 is a non-commitment and
  signals indecision.
- Do not output empty register values when the body has content. If body has at least
  one sentence of editorial framing, pick a non-factual style.
"""

PROMPT_B = PROMPT_A + _NEGATION_RULES

# State-vs-city rule replaces the India-city anchor block (the geographic
# anchor list runs from line 520-530 in run_corpus_pass.py).
_INDIA_ANCHOR_BLOCK = """- For India articles: if the article body names ANY specific city/town/district/mandal/constituency by name, you MUST populate the city field. Country must always be "India" for these.
  Anchors — Telangana: Hyderabad, Khammam, Karimnagar, Warangal, Nizamabad
  AP: Visakhapatnam, Vijayawada, Amaravati, Tirupati
  Karnataka: Bengaluru, Mysuru, Hubballi
  TN: Chennai, Madurai, Coimbatore
  Maharashtra: Mumbai, Pune, Nashik
  Kerala: Thiruvananthapuram, Kochi
  UP: Lucknow, Varanasi
  WB: Kolkata
  Gujarat: Ahmedabad
  Punjab: Chandigarh, Ludhiana"""

_STATE_VS_CITY_RULE = """- LOCATION SCOPE — state vs. city decision tree:
  1. If the article describes a STATE-WIDE policy / cabinet decision / assembly action
     / scheme rollout affecting the whole state, populate region (state) and LEAVE city=null.
     A state cabinet meeting in Hyderabad is NOT a "Hyderabad story" — it is a Telangana story.
  2. If the article describes a CITY-SPECIFIC incident (road crash, GHMC notice, local
     protest at a named landmark, a city-court verdict) populate BOTH region and city.
  3. If the article names multiple cities of equal weight, set is_primary=true on the
     city that holds the lede/headline focus and is_primary=false on the rest.
  4. National-level (centre government, Lok Sabha, Supreme Court of India in New Delhi):
     country="India", region="Delhi", city="New Delhi" only if the body specifically
     mentions a New-Delhi-bound event; otherwise region=null, city=null.

  WORKED EXAMPLE 1 (state-wide):
    title: "Telangana cabinet approves new industrial policy"
    body: "The state cabinet met at Pragathi Bhavan in Hyderabad on Tuesday..."
    correct location: {text:"Telangana", country:"India", region:"Telangana", city:null, is_primary:true}
    WRONG: putting city="Hyderabad" — the policy is state-scoped, not city-scoped.

  WORKED EXAMPLE 2 (city-specific):
    title: "Two killed in Hyderabad flyover crash"
    body: "A speeding lorry overturned on the PVNR Expressway near Attapur..."
    correct location: {text:"Hyderabad", country:"India", region:"Telangana", city:"Hyderabad", is_primary:true}
    Reason: the incident is at a specific city location, not state-scoped."""

PROMPT_C = PROMPT_B.replace(_INDIA_ANCHOR_BLOCK, _STATE_VS_CITY_RULE)

_OUTPUT_PROTOCOL = """

OUTPUT PROTOCOL (mandatory two-section response):
First emit a short REASONING section, then a JSON section. The post-processor will strip
the REASONING block and parse the JSON block only.

Format:
REASONING:
type_pick: <chosen article_type> because <one short clause>
style_pick: <chosen rhetorical_style> because <one short clause citing a trigger word/phrase>
location_scope: <state|city|national|none> because <one short clause>

JSON:
{<the full JSON object exactly matching the schema above>}

The JSON block MUST be valid JSON parseable by Python's json.loads. Do NOT wrap it
in markdown fences. The REASONING block is three lines and is for grounding only —
keep each line under 25 words."""

PROMPT_D = PROMPT_B + _OUTPUT_PROTOCOL

_ENUM_TRIGGERS = """

REGISTER TRIGGER PHRASES (use these to pick rhetorical_style — pick the FIRST that fires):
- polemical: body contains "shameful", "must", "failure", "betrayal", "disgrace",
  "outrageous", "scandalous", "criminal" (used metaphorically), "puppet", "stooge"
- sensational: body contains "shocking", "horrifying", "stunning", "bizarre",
  "explosive", "dramatic twist", "you won't believe"
- promotional: body praises subject in three or more consecutive sentences with no
  counter-position; uses "world-class", "best-in-class", "trailblazer", "visionary"
- mocking: body uses irony quotes around opponent's claims, scare-quotes ("so-called"),
  rhetorical questions implying ridicule
- sympathetic: body foregrounds suffering, uses "tragic", "heartbreaking", emphasises
  victim humanisation with first-person quotes about loss
- analytical: body uses "however", "on the other hand", "by contrast", "analysts say",
  weighs at least two competing factors explicitly
- factual: NONE of the above triggers fire AND the body is straight reportage with
  attribution; should be the LAST resort, not the default.

PRIMARY_EMOTION TRIGGERS:
- alarm: "warning", "alert", "crisis", "threat"
- approval: "welcomed", "praised", "applauded", "endorsed"
- mockery: scare quotes, sarcasm, rhetorical questions implying ridicule
- urgency: "must act now", "running out of time", "immediate"
- lament: "tragic", "heartbreaking", "loss"
- curiosity: explainer/quiz framing, "why does X matter"
- admiration: "trailblazing", "pioneering", "remarkable achievement"
- neutral: ONLY when none of the above apply — should NOT be the default for opinion/analysis."""

PROMPT_E = PROMPT_B + _ENUM_TRIGGERS


# Map variant name → English prompt. Non-English variants are constructed
# from the same body + the language-note suffix.
PROMPTS_ENGLISH = {
    "baseline": PROMPT_BASELINE,
    "A": PROMPT_A,
    "B": PROMPT_B,
    "C": PROMPT_C,
    "D": PROMPT_D,
    "E": PROMPT_E,
}

_NON_ENGLISH_SUFFIX = """

LANGUAGE NOTE: This article is in a non-English language.
FIRST internally translate the body to English.
THEN extract structured data FROM THE TRANSLATION.
Add ONE extra field to the JSON output:
  english_translation: str (a faithful English translation of the article body, max 1500 chars)
Keep names of people, places, organizations in their original transliterated form."""

PROMPTS_NON_ENGLISH = {
    name: prompt + _NON_ENGLISH_SUFFIX for name, prompt in PROMPTS_ENGLISH.items()
}


# ─────────────────────────────────────────────────────────────────────
# SAMPLE SELECTION
# ─────────────────────────────────────────────────────────────────────

_INDIA_KEYWORDS = (
    "india", "telangana", "andhra", "modi", "rahul", "kcr",
    "jagan", "hyderabad", "delhi", "mumbai", "chennai",
    "bengaluru", "kolkata", "trs", "brs", "tdp", "ysrcp",
    "bjp", "congress",
)


async def _pick_stratum(
    conn: asyncpg.Connection, where: str, limit: int, label: str,
) -> list[int]:
    rows = await conn.fetch(
        f"""
        SELECT id FROM articles
        WHERE substrate_status='ok'
          AND extraction_version=2
          AND full_text_scraped IS NOT NULL
          AND char_length(full_text_scraped) >= 120
          AND ({where})
        ORDER BY random()
        LIMIT $1
        """,
        limit,
    )
    ids = [str(r["id"]) for r in rows]
    logger.info("stratum %s: picked %d/%d", label, len(ids), limit)
    return ids


async def select_sample(conn: asyncpg.Connection) -> list[int]:
    """200-article stratified sample. Falls back to whatever the DB has."""
    if SAMPLE_IDS_PATH.exists():
        existing = [
            line.strip() for line in SAMPLE_IDS_PATH.read_text().splitlines()
            if line.strip()
        ]
        if existing:
            logger.info("reusing %d sample ids from %s", len(existing), SAMPLE_IDS_PATH)
            return existing

    not_india_clause = " AND ".join(
        f"LOWER(title) NOT LIKE '%{kw}%'" for kw in _INDIA_KEYWORDS
    )

    strata: list[tuple[str, int, str]] = [
        (
            "language_iso='en' AND (LOWER(title) LIKE '%telangana%' OR LOWER(title) LIKE '%andhra%' "
            "OR LOWER(title) LIKE '%kcr%' OR LOWER(title) LIKE '%jagan%' OR LOWER(title) LIKE '%revanth%' "
            "OR LOWER(title) LIKE '%politics%' OR LOWER(title) LIKE '%cabinet%' OR LOWER(title) LIKE '%assembly%')",
            40, "english_political",
        ),
        ("language_iso='te'", 30, "telugu"),
        (
            "language_iso='en' AND (LOWER(title) LIKE '%opinion%' OR LOWER(title) LIKE '%editorial%' "
            "OR LOWER(title) LIKE '%column%' OR LOWER(title) LIKE '%op-ed%')",
            20, "english_opinion",
        ),
        (
            "article_type='sports_result' OR LOWER(title) LIKE '%recipe%' OR LOWER(title) LIKE '%cricket%' "
            "OR LOWER(title) LIKE '%match%' OR LOWER(title) LIKE '%recipe%'",
            20, "sports_recipe",
        ),
        (
            "language_iso='en' AND LENGTH(full_text_scraped) > 4000",
            20, "long_features",
        ),
        (
            "language_iso='en' AND LENGTH(full_text_scraped) BETWEEN 200 AND 600",
            20, "short_news",
        ),
        (
            f"language_iso='en' AND {not_india_clause}",
            20, "international",
        ),
        (
            "language_iso='en' AND (LOWER(title) LIKE '%cabinet%' OR LOWER(title) LIKE '%scheme%' "
            "OR LOWER(title) LIKE '%budget%' OR LOWER(title) LIKE '%policy%' OR LOWER(title) LIKE '%state%')",
            20, "state_policy",
        ),
        ("language_iso='hi'", 10, "hindi"),
    ]

    picked: list[str] = []
    seen: set[str] = set()
    for where, limit, label in strata:
        ids = await _pick_stratum(conn, where, limit, label)
        for aid in ids:
            if aid not in seen:
                picked.append(aid)
                seen.add(aid)

    # Top-up if we're under target — pull random English ok-rows.
    if len(picked) < SAMPLE_SIZE_TARGET:
        deficit = SAMPLE_SIZE_TARGET - len(picked)
        # asyncpg parses inline numeric literals strictly — passing IDs as
        # array param avoids "trailing junk after numeric literal" errors.
        rows = await conn.fetch(
            """
            SELECT id FROM articles
            WHERE substrate_status='ok'
              AND extraction_version=2
              AND language_iso='en'
              AND full_text_scraped IS NOT NULL
              AND char_length(full_text_scraped) >= 120
              AND NOT (id = ANY($1::uuid[]))
            ORDER BY random()
            LIMIT $2
            """,
            picked, deficit,
        )
        for r in rows:
            aid = str(r["id"])
            if aid not in seen:
                picked.append(aid)
                seen.add(aid)

    picked = picked[:SAMPLE_SIZE_TARGET]
    SAMPLE_IDS_PATH.write_text("\n".join(picked))
    logger.info("sample written → %s (%d ids)", SAMPLE_IDS_PATH, len(picked))
    return picked


async def fetch_articles(
    conn: asyncpg.Connection, ids: list[int],
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT id, title, full_text_scraped, language_iso
        FROM articles WHERE id = ANY($1::uuid[])
        """,
        ids,
    )
    out = []
    for r in rows:
        d = dict(r)
        d["id"] = str(d["id"])
        out.append(d)
    return out


# ─────────────────────────────────────────────────────────────────────
# CALL + METRICS
# ─────────────────────────────────────────────────────────────────────

@dataclass
class CallResult:
    prompt: str
    article_id: str
    json_valid: bool
    latency_ms: int
    error: str | None = None
    raw_text: str = ""
    parsed: dict[str, Any] = field(default_factory=dict)


def _strip_reasoning(raw: str) -> str:
    """Variant D wraps JSON after a REASONING: block. Extract the JSON."""
    if "JSON:" in raw:
        idx = raw.rfind("JSON:")
        return raw[idx + len("JSON:"):].strip()
    return raw


def _parse_json(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    text = raw.strip()
    text = _strip_reasoning(text)
    try:
        out = json.loads(text)
        return out if isinstance(out, dict) else None
    except (TypeError, ValueError):
        pass
    if text.startswith("```"):
        text = text.strip("`")
        text = text.replace("json", "", 1).strip()
    first, last = text.find("{"), text.rfind("}")
    if 0 <= first < last:
        text = text[first:last + 1]
    try:
        out = json.loads(text)
        return out if isinstance(out, dict) else None
    except (TypeError, ValueError):
        return None


async def run_one(
    sem: asyncio.Semaphore,
    prompt_name: str,
    sys_prompt: str,
    article: dict[str, Any],
    max_tokens: int,
) -> CallResult:
    async with sem:
        start = time.monotonic()
        title = article.get("title") or ""
        lang = (article.get("language_iso") or "en").lower()
        body = article.get("full_text_scraped") or ""
        if lang in INDIC_LANGS:
            body = body[:MAX_BODY_FOR_GROQ_INDIC]
        else:
            body = body[:MAX_BODY_FOR_GROQ_ENGLISH]

        user_prompt = (
            f"TITLE: {title}\n\nBODY:\n{body}\n\n"
            "Return ONLY the JSON object."
        )
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            # Force Cerebras direct so every prompt hits the same model.
            # Variant D needs REASONING+JSON two-block format → json_response=False.
            raw = await _call_cerebras(
                messages=messages,
                groq_model="qwen/qwen3-32b",   # maps to qwen-3-235b-a22b-instruct-2507
                max_tokens=max_tokens,
                temperature=0.3,
                json_response=(prompt_name != "D"),
            )
        except (GroqCallFailed, GroqQuotaExhausted, Exception) as exc:
            latency = int((time.monotonic() - start) * 1000)
            return CallResult(
                prompt=prompt_name,
                article_id=article["id"],
                json_valid=False,
                latency_ms=latency,
                error=f"{type(exc).__name__}: {exc}",
            )
        latency = int((time.monotonic() - start) * 1000)
        parsed = _parse_json(raw)
        return CallResult(
            prompt=prompt_name,
            article_id=article["id"],
            json_valid=parsed is not None,
            latency_ms=latency,
            raw_text=raw,
            parsed=parsed or {},
        )


def classify_primary_subject(parsed: dict[str, Any], title: str) -> str:
    ps = parsed.get("primary_subject")
    if not ps or not isinstance(ps, str):
        return "null"
    ps_norm = ps.strip().lower()
    if any(ps_norm.startswith(p) for p in META_INTRO_PHRASES):
        return "meta_intro"
    if title and ps_norm == title.strip().lower():
        return "title_dup"
    return "good"


def extract_metrics(
    parsed: dict[str, Any], title: str,
) -> dict[str, Any]:
    register = parsed.get("register") or {}
    if not isinstance(register, dict):
        register = {}
    locations = parsed.get("locations") or []
    if not isinstance(locations, list):
        locations = []
    events = parsed.get("events") or []
    if not isinstance(events, list):
        events = []
    quotes = parsed.get("quotes") or []
    if not isinstance(quotes, list):
        quotes = []
    stances = parsed.get("actor_stances") or []
    if not isinstance(stances, list):
        stances = []
    claims = parsed.get("claims") or []
    if not isinstance(claims, list):
        claims = []
    numbers = parsed.get("numbers") or []
    if not isinstance(numbers, list):
        numbers = []

    cities = [
        (loc.get("city") or "").strip().lower()
        for loc in locations
        if isinstance(loc, dict) and loc.get("city")
    ]
    intensities: list[float] = []
    for s in stances:
        if not isinstance(s, dict):
            continue
        v = s.get("intensity")
        if isinstance(v, (int, float)):
            intensities.append(float(v))

    event_dates: list[tuple[bool, bool]] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        is_future = bool(ev.get("is_future"))
        has_date = bool(ev.get("date"))
        event_dates.append((has_date, is_future))

    units = [
        (n.get("unit") or "").strip()
        for n in numbers
        if isinstance(n, dict) and n.get("unit")
    ]

    return {
        "article_type": parsed.get("article_type"),
        "register_style": register.get("rhetorical_style"),
        "primary_emotion": register.get("primary_emotion"),
        "is_breaking": register.get("is_breaking"),
        "primary_subject_quality": classify_primary_subject(parsed, title),
        "num_locations": len(locations),
        "num_cities": len(cities),
        "city_names": cities,
        "num_events": len(events),
        "event_dates": event_dates,
        "num_quotes": len(quotes),
        "num_claims": len(claims),
        "num_numbers": len(numbers),
        "units": units,
        "stance_intensities": intensities,
    }


# ─────────────────────────────────────────────────────────────────────
# AGGREGATION
# ─────────────────────────────────────────────────────────────────────


def shannon_entropy(counter: Counter[str]) -> float:
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    h = 0.0
    for v in counter.values():
        if v <= 0:
            continue
        p = v / total
        h -= p * math.log2(p)
    return round(h, 3)


def aggregate(per_prompt_rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(per_prompt_rows)
    if n == 0:
        return {}
    valid_rows = [r for r in per_prompt_rows if r["json_valid"]]
    n_valid = len(valid_rows)

    type_counter: Counter[str] = Counter()
    style_counter: Counter[str] = Counter()
    primary_counter: Counter[str] = Counter()
    city_counter: Counter[str] = Counter()

    past_events_total = 0
    past_events_dated = 0
    mid_band_intensities = 0
    total_intensities = 0
    quote_sum = claim_sum = num_sum = 0
    pct_unit_canonical = 0
    pct_unit_total = 0
    latency_sum = 0

    bad_units = {"%", "rs", "rs.", "₹", "cr", "yrs", "km."}

    for r in per_prompt_rows:
        latency_sum += r["latency_ms"]
        if not r["json_valid"]:
            continue
        m = r["metrics"]
        if m["article_type"]:
            type_counter[str(m["article_type"])] += 1
        if m["register_style"]:
            style_counter[str(m["register_style"])] += 1
        primary_counter[m["primary_subject_quality"]] += 1
        for c in m["city_names"]:
            city_counter[c] += 1
        for has_date, is_future in m["event_dates"]:
            if not is_future:
                past_events_total += 1
                if has_date:
                    past_events_dated += 1
        for i in m["stance_intensities"]:
            total_intensities += 1
            if 0.4 <= i <= 0.6:
                mid_band_intensities += 1
        quote_sum += m["num_quotes"]
        claim_sum += m["num_claims"]
        num_sum += m["num_numbers"]
        for u in m["units"]:
            pct_unit_total += 1
            if u.lower() in bad_units:
                pass
            else:
                pct_unit_canonical += 1

    pct = lambda num, den: round(100 * num / den, 1) if den else 0.0  # noqa: E731

    return {
        "n_total": n,
        "n_valid": n_valid,
        "json_valid_pct": pct(n_valid, n),
        "type_entropy": shannon_entropy(type_counter),
        "style_entropy": shannon_entropy(style_counter),
        "pct_news": pct(type_counter.get("news", 0), n_valid),
        "pct_factual": pct(style_counter.get("factual", 0), n_valid),
        "pct_subject_good": pct(primary_counter.get("good", 0), n_valid),
        "pct_subject_meta": pct(primary_counter.get("meta_intro", 0), n_valid),
        "pct_subject_titledup": pct(primary_counter.get("title_dup", 0), n_valid),
        "pct_subject_null": pct(primary_counter.get("null", 0), n_valid),
        "pct_past_dated": pct(past_events_dated, past_events_total),
        "pct_intensity_midband": pct(mid_band_intensities, total_intensities),
        "pct_canonical_units": pct(pct_unit_canonical, pct_unit_total),
        "pct_hyderabad": pct(
            city_counter.get("hyderabad", 0), n_valid,
        ),
        "mean_quotes": round(quote_sum / max(n_valid, 1), 2),
        "mean_claims": round(claim_sum / max(n_valid, 1), 2),
        "mean_numbers": round(num_sum / max(n_valid, 1), 2),
        "mean_latency_ms": round(latency_sum / max(n, 1), 0),
    }


def format_summary(agg_by_prompt: dict[str, dict[str, Any]]) -> str:
    metrics = [
        ("n_valid",            "n_valid (of total)",         "higher"),
        ("json_valid_pct",     "JSON valid %",               "higher"),
        ("type_entropy",       "type entropy (bits)",        "higher"),
        ("style_entropy",      "style entropy (bits)",       "higher"),
        ("pct_news",           "% news",                     "lower~70"),
        ("pct_factual",        "% factual",                  "lower"),
        ("pct_subject_good",   "% subject good",             "higher"),
        ("pct_subject_meta",   "% subject meta-intro",       "lower"),
        ("pct_subject_titledup", "% subject title-dup",      "lower"),
        ("pct_past_dated",     "% past events dated",        "higher"),
        ("pct_intensity_midband", "% intensity in 0.4-0.6",  "lower"),
        ("pct_canonical_units", "% canonical units",         "higher"),
        ("pct_hyderabad",      "% w/ Hyderabad",             "lower"),
        ("mean_quotes",        "mean quotes",                "higher"),
        ("mean_claims",        "mean claims",                "higher"),
        ("mean_numbers",       "mean numbers",               "higher"),
        ("mean_latency_ms",    "mean latency (ms)",          "lower"),
    ]
    prompt_names = list(agg_by_prompt.keys())
    header = f"{'metric':<28} {'goal':<10} " + " ".join(f"{p:>10}" for p in prompt_names)
    lines = [header, "-" * len(header)]
    for key, label, goal in metrics:
        row = f"{label:<28} {goal:<10} "
        row += " ".join(
            f"{agg_by_prompt[p].get(key, '-'):>10}" for p in prompt_names
        )
        lines.append(row)
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# DRIVER
# ─────────────────────────────────────────────────────────────────────


def _flush_partial(raw_rows: list[dict[str, Any]]) -> None:
    """Append-mode flush so we never lose progress on crash."""
    with OUTPUT_RAW.open("w") as fh:
        for r in raw_rows:
            fh.write(json.dumps(r, default=str, ensure_ascii=False) + "\n")


async def main() -> None:
    dsn = os.getenv("DATABASE_URL_SYNC") or os.getenv("DATABASE_URL", "")
    dsn = dsn.replace("postgresql+asyncpg", "postgresql")
    if not dsn:
        raise SystemExit("DATABASE_URL not set")

    logger.info("connecting to DB...")
    conn = await asyncpg.connect(dsn)
    try:
        sample_ids = await select_sample(conn)
        articles = await fetch_articles(conn, sample_ids)
    finally:
        await conn.close()

    logger.info("loaded %d articles; running %d prompts × %d articles = %d calls",
                len(articles), len(PROMPTS_ENGLISH), len(articles),
                len(PROMPTS_ENGLISH) * len(articles))

    sem = asyncio.Semaphore(CONCURRENCY)

    tasks: list[asyncio.Task[CallResult]] = []
    for art in articles:
        lang = (art.get("language_iso") or "en").lower()
        is_non_english = lang != "en"
        prompt_map = PROMPTS_NON_ENGLISH if is_non_english else PROMPTS_ENGLISH
        max_tokens = 4500 if is_non_english else 3000
        for prompt_name, sys_prompt in prompt_map.items():
            tasks.append(asyncio.create_task(
                run_one(sem, prompt_name, sys_prompt, art, max_tokens),
            ))

    raw_rows: list[dict[str, Any]] = []
    done = 0
    for fut in asyncio.as_completed(tasks):
        res = await fut
        done += 1
        # Re-lookup the title for primary-subject classification.
        title = next(
            (a.get("title", "") for a in articles if a["id"] == res.article_id),
            "",
        )
        metrics = (
            extract_metrics(res.parsed, title)
            if res.json_valid else None
        )
        raw_rows.append({
            "prompt": res.prompt,
            "article_id": res.article_id,
            "json_valid": res.json_valid,
            "latency_ms": res.latency_ms,
            "error": res.error,
            "metrics": metrics,
            "raw_text": res.raw_text[:4000],   # truncate so JSONL stays sane
        })
        if done % PARTIAL_FLUSH_EVERY == 0:
            _flush_partial(raw_rows)
            logger.info("flushed %d/%d", done, len(tasks))

    _flush_partial(raw_rows)

    # Aggregate per prompt
    agg_by_prompt: dict[str, dict[str, Any]] = {}
    for prompt_name in PROMPTS_ENGLISH:
        prompt_rows = [r for r in raw_rows if r["prompt"] == prompt_name]
        agg_by_prompt[prompt_name] = aggregate(prompt_rows)

    summary = format_summary(agg_by_prompt)
    OUTPUT_SUMMARY.write_text(summary)
    print(summary)


if __name__ == "__main__":
    asyncio.run(main())
