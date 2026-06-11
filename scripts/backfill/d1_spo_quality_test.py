"""d1_spo_quality_test.py — verify the D1 SPO-prompt patch on 50 sample articles.

Runs inside the rig-backend container. Pulls 50 recent substrate=ok articles,
calls the unified LLM pool with the NEW patched system prompt (inline below
so we don't have to deploy code first), parses the JSON, and emits a quality
matrix:

  - SPO populate rate per claim
  - Counts for every other field (article_type, locations, events, quotes,
    actor_stances, numbers, register, summaries) so we can confirm nothing
    degraded vs the v3 baseline.

USAGE:
  docker exec rig-backend python /tmp/d1_spo_quality_test.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections import Counter

sys.path.insert(0, "/app")
from sqlalchemy import text
from backend.database import get_db
from backend.nlp.groq_client import (
    FAST_MODEL,
    GroqCallFailed,
    GroqQuotaExhausted,
    call_groq,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("d1_test")

SAMPLE_SIZE = 50
MAX_BODY = 2400

# ─────────────────────────────────────────────────────────────────────
# PATCHED PROMPT (mirrors what was just edited in run_corpus_pass.py)
# ─────────────────────────────────────────────────────────────────────

GROQ_SYS = """Extract structured intel from this news article. Output JSON ONLY matching the schema.

REQUIRED fields (ALL must be present):
  article_type: one of [news, opinion, analysis, explainer, listicle, horoscope, recipe, live_blog, photo_essay, interview, press_release, sports_result, other]
  primary_subject: 1 short sentence describing what the article is FUNDAMENTALLY about
  summaries: {preview: str<=50ch, snippet: str<=200ch, executive: str<=1000ch}
  locations: [{text: str, country: str|null, region: str|null, city: str|null, is_primary: bool}] max 5, can be []
  events: [{date: YYYY-MM-DD|null, description: <=14 words, event_type: announcement|meeting|filing|statement|protest|release|election|accident|market_event|legal|sports_result|other, actors: [names], is_future: bool}] max 6, can be []
  quotes: [{speaker: str, text: str, context: press_conference|interview|tweet|statement|parliament|court|press_release|article|other, is_verbatim: bool}] max 5, can be []
  actor_stances: [{actor: str, stance: supportive|neutral|critical, intensity: 0-1}] max 5, can be []
  claims: [{subject: str, predicate: str, object: str, text: str, claimant: article|<name>, type: attributable|asserted|disputed, verifiable: bool}] max 5, can be []
  numbers: [{value: str, unit: str|null, context: str}] max 5, can be []
  register: {rhetorical_style: factual|analytical|polemical|sympathetic|mocking|promotional|sensational, primary_emotion: neutral|alarm|approval|mockery|urgency|lament|curiosity|admiration, is_breaking: bool}

RULES:
- country MUST be the full English name of a sovereign nation.
- claims: factual assertions made by article OR by named speakers. EVERY claim MUST be decomposed into subject + predicate + object (the SPO triple). The flat `text` field carries the natural-language form.
    Examples:
      "BJP won the Karnataka election"            -> {subject: "BJP", predicate: "won", object: "the Karnataka election", text: "BJP won the Karnataka election", claimant: "article", type: "asserted", verifiable: true}
      "Modi announced a new agriculture policy"   -> {subject: "Narendra Modi", predicate: "announced", object: "a new agriculture policy", text: "Modi announced a new agriculture policy", claimant: "article", type: "asserted", verifiable: false}
      "GDP growth fell to 5.2% in Q3"             -> {subject: "GDP growth", predicate: "fell to", object: "5.2% in Q3", text: "GDP growth fell to 5.2% in Q3", claimant: "article", type: "asserted", verifiable: true}
      "KCR said the bill is unconstitutional"     -> {subject: "the bill", predicate: "is", object: "unconstitutional", text: "KCR said the bill is unconstitutional", claimant: "K. Chandrashekar Rao", type: "attributable", verifiable: false}
    subject  = the entity the claim is ABOUT (NEVER "article", NEVER a bare pronoun). Resolve pronouns to their referent.
    predicate = the verb/relation phrase ("announced", "denied", "promised to", "rose to", "is").
    object   = the target / value / recipient / property.
    claimant = WHO is making the claim ("article" if reporter's assertion; speaker name if attributed).
    If you cannot identify subject, predicate, AND object cleanly, OMIT the claim. Do NOT emit claims with empty/null SPO parts.
- actor_stances: per named entity, what is the article's posture? stance='neutral' -> intensity MUST be 0.0.
- quotes: is_verbatim=true only for quoted text; use underscore context enums (press_release, press_conference).
- numbers: every value with unit; value as STRING.
- NEVER return the literal string "null". Use JSON null.
- Output ONLY the JSON object. No markdown fences, no prose."""


async def extract_one(article_id: str, title: str, body: str) -> dict | None:
    user = f"TITLE: {title}\n\nBODY:\n{body[:MAX_BODY]}\n\nReturn ONLY the JSON object."
    try:
        raw = await call_groq(
            system=GROQ_SYS,
            user=user,
            model=FAST_MODEL,
            task_type="profile_extraction",
            json_response=True,
            max_tokens_override=3000,
        )
    except (GroqCallFailed, GroqQuotaExhausted) as e:
        log.warning("LLM call failed on %s: %s", article_id, str(e)[:120])
        return None
    raw_s = (raw or "").strip()
    try:
        return json.loads(raw_s)
    except json.JSONDecodeError:
        # strip fences + isolate outer braces
        first = raw_s.find("{")
        last = raw_s.rfind("}")
        if first >= 0 and last > first:
            try:
                return json.loads(raw_s[first:last + 1])
            except json.JSONDecodeError:
                pass
        log.warning("JSON parse failed on %s. raw[:160]=%r", article_id, raw_s[:160])
        return None


def analyze(article_id: str, parsed: dict, report: dict) -> None:
    """Tally the parsed JSON into the global quality matrix."""
    report["successful_extractions"] += 1
    # SPO presence per claim
    claims = parsed.get("claims") or []
    for c in claims:
        if not isinstance(c, dict):
            continue
        report["claims_total"] += 1
        s = (c.get("subject") or "").strip()
        p = (c.get("predicate") or "").strip()
        o = (c.get("object") or "").strip()
        t = (c.get("text") or "").strip()
        if s:
            report["claim_subject_filled"] += 1
        if p:
            report["claim_predicate_filled"] += 1
        if o:
            report["claim_object_filled"] += 1
        if s and p and o:
            report["claim_spo_complete"] += 1
        if t:
            report["claim_text_filled"] += 1
        # Catch the bad cases the rule was supposed to prevent
        if s.lower() in ("article", "this", "it", "they"):
            report["claim_subject_bad"] += 1
        if s and not p and not o:
            report["claim_subject_only_no_pred_obj"] += 1
    # Field presence for the OTHER fields — to confirm no regression
    for field, cnt_key in [
        ("article_type", "has_article_type"),
        ("primary_subject", "has_primary_subject"),
        ("summaries", "has_summaries"),
        ("locations", "has_locations_nonempty"),
        ("events", "has_events_nonempty"),
        ("quotes", "has_quotes_nonempty"),
        ("actor_stances", "has_stances_nonempty"),
        ("numbers", "has_numbers_nonempty"),
        ("register", "has_register"),
    ]:
        v = parsed.get(field)
        if field in ("article_type", "primary_subject", "register", "summaries"):
            if v:
                report[cnt_key] += 1
        else:
            if isinstance(v, list) and len(v) > 0:
                report[cnt_key] += 1
    # Per-field counts (for completeness checks against v3 baseline)
    report["sum_locations"] += len(parsed.get("locations") or [])
    report["sum_events"] += len(parsed.get("events") or [])
    report["sum_quotes"] += len(parsed.get("quotes") or [])
    report["sum_stances"] += len(parsed.get("actor_stances") or [])
    report["sum_numbers"] += len(parsed.get("numbers") or [])
    # article_type distribution
    at = parsed.get("article_type") or "missing"
    report["article_types"][at] = report["article_types"].get(at, 0) + 1


async def main() -> int:
    log.info("D1 SPO quality test — sampling %d articles", SAMPLE_SIZE)
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT id::text AS aid,
                   COALESCE(title, '') AS title,
                   COALESCE(NULLIF(full_text_translated, ''), full_text_scraped) AS body
              FROM articles
             WHERE substrate_status = 'ok'
               AND LENGTH(COALESCE(full_text_translated, full_text_scraped, '')) > 400
               AND collected_at > NOW() - INTERVAL '7 days'
             ORDER BY RANDOM()
             LIMIT :n
        """), {"n": SAMPLE_SIZE})).mappings().all()
    log.info("fetched %d sample articles", len(rows))

    report = {
        "successful_extractions": 0,
        "claims_total": 0,
        "claim_subject_filled": 0,
        "claim_predicate_filled": 0,
        "claim_object_filled": 0,
        "claim_text_filled": 0,
        "claim_spo_complete": 0,
        "claim_subject_bad": 0,
        "claim_subject_only_no_pred_obj": 0,
        "has_article_type": 0,
        "has_primary_subject": 0,
        "has_summaries": 0,
        "has_locations_nonempty": 0,
        "has_events_nonempty": 0,
        "has_quotes_nonempty": 0,
        "has_stances_nonempty": 0,
        "has_numbers_nonempty": 0,
        "has_register": 0,
        "sum_locations": 0,
        "sum_events": 0,
        "sum_quotes": 0,
        "sum_stances": 0,
        "sum_numbers": 0,
        "article_types": {},
    }

    # 4-way concurrency (matches LLM pool ceiling), keeps test ~2-3 min
    sem = asyncio.Semaphore(4)

    async def worker(r):
        async with sem:
            parsed = await extract_one(r["aid"], r["title"], r["body"] or "")
            if parsed:
                analyze(r["aid"], parsed, report)
            else:
                report.setdefault("failed_extractions", 0)
                report["failed_extractions"] = report.get("failed_extractions", 0) + 1

    await asyncio.gather(*(worker(r) for r in rows))

    # ── Print quality matrix ──
    print("\n" + "=" * 60)
    print("D1 SPO QUALITY TEST RESULTS")
    print("=" * 60)
    print(f"Sample size: {len(rows)}")
    print(f"Successful extractions: {report['successful_extractions']}")
    print(f"Failed (JSON or LLM): {report.get('failed_extractions', 0)}")
    print()
    print("── CLAIMS (D1 target) ──")
    n_claims = report["claims_total"]
    print(f"Total claims: {n_claims}")
    if n_claims:
        print(f"  subject filled : {report['claim_subject_filled']:>3} ({report['claim_subject_filled']/n_claims*100:.1f}%)")
        print(f"  predicate fill : {report['claim_predicate_filled']:>3} ({report['claim_predicate_filled']/n_claims*100:.1f}%)")
        print(f"  object filled  : {report['claim_object_filled']:>3} ({report['claim_object_filled']/n_claims*100:.1f}%)")
        print(f"  text filled    : {report['claim_text_filled']:>3} ({report['claim_text_filled']/n_claims*100:.1f}%)")
        print(f"  SPO complete   : {report['claim_spo_complete']:>3} ({report['claim_spo_complete']/n_claims*100:.1f}%)  <-- target >= 80%")
        print(f"  bad subjects   : {report['claim_subject_bad']:>3} (the/article/it/they)")
        print(f"  subj-only      : {report['claim_subject_only_no_pred_obj']:>3} (missed predicate+object)")
    print()
    print("── OTHER FIELDS (regression watch) ──")
    n = report["successful_extractions"] or 1
    print(f"  article_type   : {report['has_article_type']}/{n} ({report['has_article_type']/n*100:.0f}%)")
    print(f"  primary_subject: {report['has_primary_subject']}/{n} ({report['has_primary_subject']/n*100:.0f}%)")
    print(f"  summaries      : {report['has_summaries']}/{n} ({report['has_summaries']/n*100:.0f}%)")
    print(f"  locations>0    : {report['has_locations_nonempty']}/{n} ({report['has_locations_nonempty']/n*100:.0f}%) [avg {report['sum_locations']/n:.2f}/article]")
    print(f"  events>0       : {report['has_events_nonempty']}/{n} ({report['has_events_nonempty']/n*100:.0f}%) [avg {report['sum_events']/n:.2f}/article]")
    print(f"  quotes>0       : {report['has_quotes_nonempty']}/{n} ({report['has_quotes_nonempty']/n*100:.0f}%) [avg {report['sum_quotes']/n:.2f}/article]")
    print(f"  stances>0      : {report['has_stances_nonempty']}/{n} ({report['has_stances_nonempty']/n*100:.0f}%) [avg {report['sum_stances']/n:.2f}/article]")
    print(f"  numbers>0      : {report['has_numbers_nonempty']}/{n} ({report['has_numbers_nonempty']/n*100:.0f}%) [avg {report['sum_numbers']/n:.2f}/article]")
    print(f"  register       : {report['has_register']}/{n} ({report['has_register']/n*100:.0f}%)")
    print()
    print("── article_type distribution ──")
    for k, v in sorted(report["article_types"].items(), key=lambda x: -x[1]):
        print(f"  {k:>20}: {v}")
    print("=" * 60)
    # Surface a single verdict
    if n_claims == 0:
        print("VERDICT: NO CLAIMS — prompt or input issue, INVESTIGATE")
        return 2
    spo_rate = report["claim_spo_complete"] / n_claims
    if spo_rate >= 0.80:
        print(f"VERDICT: PASS — {spo_rate*100:.1f}% SPO completeness, ready to deploy")
        return 0
    elif spo_rate >= 0.50:
        print(f"VERDICT: PARTIAL — {spo_rate*100:.1f}% SPO — usable, may need prompt refinement")
        return 1
    else:
        print(f"VERDICT: FAIL — {spo_rate*100:.1f}% SPO, refine prompt")
        return 3


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
