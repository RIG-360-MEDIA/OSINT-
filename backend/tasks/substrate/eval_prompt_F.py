"""
JSON-extraction prompt evaluation harness — 3-way head-to-head (F vs C vs baseline).

Self-contained — does NOT touch run_corpus_pass.py production logic. Does NOT
modify the existing eval_prompts.py (kept as historical record).

Reuses the same 100 article IDs at /tmp/eval_v2_sample_ids.txt so the F-vs-C-vs
baseline comparison is on an identical sample. Runs 300 calls (100 articles ×
3 prompts) through Ollama qwen3:30b-a3b at http://100.92.126.27:11434 with
asyncio.Semaphore(2) (matches OLLAMA_NUM_PARALLEL=2).

Outputs:
  /tmp/eval_F_raw.jsonl   — raw per-call results
  /tmp/eval_F_summary.txt — 3-column comparison table
  stdout: same summary

Run inside the rig-backend container:

    docker exec rig-backend python3 -u -m backend.tasks.substrate.eval_prompt_F
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
import httpx

from backend.tasks.substrate.run_corpus_pass import (
    GROQ_SYS,
    INDIC_LANGS,
    MAX_BODY_FOR_GROQ_ENGLISH,
    MAX_BODY_FOR_GROQ_INDIC,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("eval_prompt_F")


# ─────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────

EVAL_MODEL = "qwen3:30b-a3b"
OLLAMA_URL = "http://100.92.126.27:11434/api/chat"

CONCURRENCY = 2
PARTIAL_FLUSH_EVERY = 50

OUTPUT_RAW = Path("/tmp/eval_F_raw.jsonl")
OUTPUT_SUMMARY = Path("/tmp/eval_F_summary.txt")
SAMPLE_IDS_PATH = Path("/tmp/eval_v2_sample_ids.txt")  # reuse v2 sample

META_INTRO_PHRASES = (
    "the article", "this article", "it is about",
    "it discusses", "this is",
)


# ─────────────────────────────────────────────────────────────────────
# PROMPT VARIANTS — baseline, C (prior winner), F (C + date rule + style)
# ─────────────────────────────────────────────────────────────────────

# Snippet stripped from baseline → A onwards.
EMPTY_JUNK_LINE = (
    "- If article is empty/junk: article_type=other, all arrays empty, "
    "register defaults to neutral/factual.\n"
)

PROMPT_BASELINE = GROQ_SYS

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
  5. FEW-SHOT — "Telangana cabinet meets in Pragathi Bhavan, Hyderabad to approve
     metro phase-2": region="Telangana", city=null (state-scoped policy).
     "Two children killed in Banjara Hills road crash": region="Telangana",
     city="Hyderabad" (city-specific incident).
     "KCR addresses BRS rally in Karimnagar": region="Telangana",
     city="Karimnagar" (city-specific event).
"""

PROMPT_C = PROMPT_B.replace(_INDIA_ANCHOR_BLOCK, _STATE_VS_CITY_RULE)

# ── PROMPT_F = PROMPT_C + event-date rule + style anti-default guidance ─────
_EVENT_DATE_RULE = """
EVENT DATE RULE:
- For past events (is_future=false): if the article text mentions any date,
  month, day-of-week, or relative time reference ("yesterday", "last week",
  "Sunday", "two days ago", "in October", "during the monsoon"), you MUST
  populate event_date with the resolved YYYY-MM-DD.
- Use event_date=null ONLY when the article body contains zero date references
  for that event.
- Today's date for resolving relative references: 2026-05-14.

STYLE GUIDANCE (anti-default):
- "factual" is the most common label but ALSO the most over-used. Before
  picking factual, check if the article uses:
  * charged adjectives ("shameful", "disgrace", "must", "failure", "betrayal") → polemical
  * "however"/"on the other hand"/causal weighing → analytical
  * "BREAKING:" / urgency tone without substance → sensational
  * praise without counterpoints → promotional
- If ANY of these triggers are present, do NOT pick factual.
"""

PROMPT_F = PROMPT_C + _EVENT_DATE_RULE


PROMPTS = {
    "baseline": PROMPT_BASELINE,
    "C": PROMPT_C,
    "F": PROMPT_F,
}


# ─────────────────────────────────────────────────────────────────────
# SAMPLE
# ─────────────────────────────────────────────────────────────────────

async def load_sample_ids() -> list[str]:
    if not SAMPLE_IDS_PATH.exists():
        raise SystemExit(f"sample ids file missing: {SAMPLE_IDS_PATH}")
    ids = [
        line.strip() for line in SAMPLE_IDS_PATH.read_text().splitlines()
        if line.strip()
    ]
    if not ids:
        raise SystemExit(f"sample ids file empty: {SAMPLE_IDS_PATH}")
    logger.info("reusing %d sample ids from %s", len(ids), SAMPLE_IDS_PATH)
    return ids


async def fetch_articles(
    conn: asyncpg.Connection, ids: list[str],
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT id, title, full_text_scraped, language_iso
        FROM articles WHERE id = ANY($1::uuid[])
        """,
        ids,
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["id"] = str(d["id"])
        out.append(d)
    return out


# ─────────────────────────────────────────────────────────────────────
# CALL
# ─────────────────────────────────────────────────────────────────────

class OllamaCallFailed(RuntimeError):
    """Raised when Ollama HTTP call fails or returns malformed body."""


async def call_ollama(
    system_prompt: str,
    user_msg: str,
    max_tokens: int = 4000,
) -> tuple[str, float]:
    """Send a chat request to Ollama on TRIJYA-7. Returns (content, latency_ms)."""
    body = {
        "model": EVAL_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "stream": False,
        "think": False,
        "format": "json",
        "options": {
            "num_predict": max_tokens,
            "num_ctx": 8192,
            "temperature": 0.1,
        },
    }
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(OLLAMA_URL, json=body)
        r.raise_for_status()
        data = r.json()
    latency_ms = (time.perf_counter() - t0) * 1000.0
    msg = data.get("message") or {}
    content = msg.get("content") if isinstance(msg, dict) else None
    if not isinstance(content, str):
        raise OllamaCallFailed(f"missing message.content; keys={list(data.keys())}")
    return content, latency_ms


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
        try:
            raw, _ = await call_ollama(
                system_prompt=sys_prompt,
                user_msg=user_prompt,
                max_tokens=max_tokens,
            )
        except Exception as exc:  # noqa: BLE001 - capture all backend errors
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


# ─────────────────────────────────────────────────────────────────────
# METRICS
# ─────────────────────────────────────────────────────────────────────

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
        # F-prompt asks for either `event_date` or legacy `date`. Accept both
        # so we don't unfairly penalise C (which only knows `date`).
        has_date = bool(ev.get("date") or ev.get("event_date"))
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
    with OUTPUT_RAW.open("w") as fh:
        for r in raw_rows:
            fh.write(json.dumps(r, default=str, ensure_ascii=False) + "\n")


async def main() -> None:
    dsn = os.getenv("DATABASE_URL_SYNC") or os.getenv("DATABASE_URL", "")
    dsn = dsn.replace("postgresql+asyncpg", "postgresql")
    if not dsn:
        raise SystemExit("DATABASE_URL not set")

    sample_ids = await load_sample_ids()

    logger.info("connecting to DB...")
    conn = await asyncpg.connect(dsn)
    try:
        articles = await fetch_articles(conn, sample_ids)
    finally:
        await conn.close()

    logger.info(
        "loaded %d articles; running %d prompts × %d articles = %d calls",
        len(articles), len(PROMPTS), len(articles),
        len(PROMPTS) * len(articles),
    )

    sem = asyncio.Semaphore(CONCURRENCY)

    tasks: list[asyncio.Task[CallResult]] = []
    task_prompt_lookup: dict[asyncio.Task[CallResult], str] = {}
    for art in articles:
        lang = (art.get("language_iso") or "en").lower()
        max_tokens = 4500 if lang != "en" else 4000
        for prompt_name, sys_prompt in PROMPTS.items():
            t = asyncio.create_task(
                run_one(sem, prompt_name, sys_prompt, art, max_tokens),
            )
            task_prompt_lookup[t] = prompt_name
            tasks.append(t)

    raw_rows: list[dict[str, Any]] = []
    done = 0
    for fut in asyncio.as_completed(tasks):
        try:
            res = await fut
        except Exception as exc:  # noqa: BLE001 - defensive; run_one should catch
            # Recover prompt_name from lookup so failures still get attributed.
            prompt_name = task_prompt_lookup.get(fut, "unknown")  # type: ignore[arg-type]
            logger.error("task raised under prompt=%s: %s", prompt_name, exc)
            raw_rows.append({
                "prompt": prompt_name,
                "article_id": "unknown",
                "json_valid": False,
                "latency_ms": 0,
                "error": f"task_raised:{type(exc).__name__}: {exc}",
                "metrics": None,
                "raw_text": "",
            })
            done += 1
            continue
        done += 1
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
            "raw_text": res.raw_text[:4000],
        })
        if done % PARTIAL_FLUSH_EVERY == 0:
            _flush_partial(raw_rows)
            logger.info("flushed %d/%d", done, len(tasks))

    _flush_partial(raw_rows)

    # Aggregate per prompt (preserves ordering: baseline, C, F).
    agg_by_prompt: dict[str, dict[str, Any]] = {}
    for prompt_name in PROMPTS:
        prompt_rows = [r for r in raw_rows if r["prompt"] == prompt_name]
        agg_by_prompt[prompt_name] = aggregate(prompt_rows)

    summary = format_summary(agg_by_prompt)
    OUTPUT_SUMMARY.write_text(summary)
    print(summary)


if __name__ == "__main__":
    asyncio.run(main())
