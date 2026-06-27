"""_worldwide_gen_sample.py — FIRST real run of the Worldwide content-gen recipe on _v8 stories.

Implements the LOCKED recipe (docs/plans/content-gen-decisions-2026-06-12.md +
faithfulness-verifier-spec-2026-06-12.md):

  load fact-ledger (story_clusters_v8 anchor + facts/quotes/timeline/geo/stance/sources)
  -> Guard C (one event or several? -> HOLD if SEVERAL)
  -> generate Hybrid A (Persona-voiced Chronological, Atlantic voice, ledger-grounded,
     dominant-event-only [Guard B], never pad, numeric-disagreement -> range, fresh hed)
  -> faithfulness verify (decompose -> entail vs the ledger; FAIL on any HIGH-risk unit
     that is UNSUPPORTED or CONTRADICTED)
  -> fail -> retry (N=2 for A) -> fall back to Hybrid B (Cited-Ledger) -> else flag extractive.

Models: gpt-oss-120b for prose (locked); qwen3-32b for the JSON verifier + Guard C.
READ-ONLY on the DB. Writes samples to /app/scripts/_ww_out (= host /root/rig/scripts/_ww_out).

Run inside the backend container:
    docker exec rig-backend python /app/scripts/_worldwide_gen_sample.py
Optional: pass story_ids as args to override the default set.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from backend.database import get_db  # noqa: E402
from backend.nlp.groq_client import call_groq  # noqa: E402

# ── Config ───────────────────────────────────────────────────────────────────
GEN_MODEL = os.getenv("WW_GEN_MODEL", "openai/gpt-oss-120b")
# gpt-oss-120b is the headroom model (heavy default models are near daily cap);
# json_response=True keeps the Guard-C/verify JSON clean despite gpt-oss verbosity.
VERIFY_MODEL = os.getenv("WW_VERIFY_MODEL", "openai/gpt-oss-120b")
OUT_DIR = Path(os.getenv("WW_OUT", "/app/scripts/_ww_out"))
GEN_TOKENS = int(os.getenv("WW_GEN_TOKENS", "4200"))
CALL_TIMEOUT = float(os.getenv("WW_CALL_TIMEOUT", "120"))
MAX_A_TRIES = 2

DEFAULT_STORY_IDS = [
    "5062a85f-6b03-4141-b0d5-cd1da818416c",  # SpaceX IPO valuation        BUSINESS/US
    "c7b0d196-306c-4d12-8106-a1fb77d55269",  # Ebola centre torched, DRC   HEALTH/CD
    "2bcd6bbb-64c1-4a05-966d-91f116afffe7",  # Stokes dropped / Root capt  SPORTS/GB
    "5eb9ecf2-7b69-4305-a8c2-69b87c893734",  # Judge blocks Trump immigr.  LEGAL/US
    "37b5c988-2f63-4e14-ac66-94f76cade4b0",  # Pentagon: Iran strikes      INTL  (mega -> Guard C)
]

# ── Prompts ──────────────────────────────────────────────────────────────────
SYS_HYBRID_A = (
    "You are a staff writer for a serious international newspaper (Atlantic / Reuters "
    "house style): measured, precise, neutral, narrative but never breathless. You write "
    "ONE news article from a STRUCTURED FACT-LEDGER that was distilled from many sources.\n\n"
    "ABSOLUTE RULES (any violation is a failure):\n"
    "1. GROUND EVERYTHING IN THE LEDGER. Use only facts, numbers, names, dates and quotes "
    "present in the ledger. Never add anything from outside it or from your own knowledge.\n"
    "2. ONE EVENT ONLY. If the ledger appears to mix several distinct events, write only the "
    "single DOMINANT event and ignore the rest. Never blend two stories into one.\n"
    "3. NUMBERS: use a number only with its unit and only if the ledger supports it. If the "
    "ledger gives a range (min differs from max) for a quantity, report the RANGE "
    "(\"between X and Y\") -- never invent a single point value.\n"
    "4. QUOTES: use a quote only if it appears in the ledger's QUOTES section, and attribute "
    "it to the speaker the ledger names. Never fabricate or reassign a quote.\n"
    "5. LENGTH FOLLOWS THE MATERIAL. Do not pad. A rich story earns ~600-1000 words; a thin "
    "one stays short. Never invent connective detail to reach a length.\n"
    "6. CHRONOLOGY. Where the ledger implies a sequence, tell it as a development arc, not a list.\n"
    "7. HEADLINE. Write a fresh, neutral, accurate headline -- do not copy a source headline.\n\n"
    "OUTPUT EXACTLY this shape and nothing else:\n"
    "HEADLINE: <neutral headline, <=14 words>\n"
    "DECK: <one-sentence summary, <=30 words>\n"
    "---\n"
    "<the article body as prose paragraphs>"
)

SYS_HYBRID_B = (
    "You are a staff writer for a serious international newspaper (Atlantic / Reuters house "
    "style). You write ONE SHORT, scrupulously grounded news item from a STRUCTURED "
    "FACT-LEDGER that is THIN or single-source. Honesty over drama.\n\n"
    "ABSOLUTE RULES (any violation is a failure):\n"
    "1. GROUND EVERYTHING IN THE LEDGER -- nothing from outside it.\n"
    "2. STAY SHORT. Write only what the ledger supports; if that is three sentences, write "
    "three sentences. Never pad, never dramatize, never invent detail to reach a length.\n"
    "3. BE HONEST WHEN THIN. If the ledger is sparse or a claim is single-source, say so "
    "plainly (e.g. 'according to a single report') rather than asserting it as settled.\n"
    "4. NUMBERS only with units and only if supported; ranges reported as ranges.\n"
    "5. QUOTES only from the ledger's QUOTES section, attributed to the named speaker.\n"
    "6. HEADLINE: fresh, neutral, accurate; do not copy a source headline.\n\n"
    "OUTPUT EXACTLY this shape and nothing else:\n"
    "HEADLINE: <neutral headline, <=14 words>\n"
    "DECK: <one-sentence summary, <=30 words>\n"
    "---\n"
    "<the article body as prose paragraphs>"
)

SYS_GUARD_C = (
    "You are a precise news editor. Given a fact-ledger for a supposed single news story, decide "
    "whether it is ONE news event or SEVERAL genuinely DISTINCT, unrelated events bundled together.\n"
    "Count as ONE event: the core incident PLUS its facets — reactions, statements, consequences, "
    "casualties, follow-ups, updates, analysis, different angles, and coverage of the SAME incident "
    "in multiple outlets or languages. A single match, deal, disaster, launch, arrest, or "
    "announcement reported many ways — and the reactions to it — is ONE event.\n"
    "Answer SEVERAL ONLY when the ledger genuinely mixes UNRELATED events that merely share a topic, "
    "person, team, film, or place — e.g. two different matches, two different films that share an "
    "actor, a film launch plus an unrelated controversy, or two different crimes in the same city. "
    "When in doubt, prefer ONE.\n"
    "Return STRICT JSON, no prose, no fences:\n"
    '{"verdict":"ONE"|"SEVERAL","dominant":"<one-line description of the dominant event>",'
    '"others":["<other distinct event>", ...]}'
)

SYS_VERIFY = (
    "You are a strict FAITHFULNESS checker. You are given (1) a SOURCE FACT-LEDGER and (2) an "
    "ARTICLE written from it. For every checkable unit in the article -- every number, every "
    "quote, every claim about a named person or organization -- decide whether it is "
    "SUPPORTED by the ledger, CONTRADICTED by it, or UNSUPPORTED (not findable in the ledger). "
    "Judge ONLY against the ledger, NEVER against your own world knowledge: 'sounds true' is "
    "irrelevant; the only question is whether THIS ledger supports it.\n\n"
    "Risk tiers: HIGH = numbers, quotes, claims about named living people/orgs (libel risk). "
    "MED = summary/paraphrase statements. LOW = topic/category/framing.\n\n"
    "Return STRICT JSON, no prose, no fences:\n"
    '{"units":[{"text":"<unit, <=160 chars>","type":"number|quote|claim|entity",'
    '"risk":"HIGH|MED|LOW","status":"SUPPORTED|CONTRADICTED|UNSUPPORTED"}],'
    '"verdict":"pass"|"fail"}\n'
    "verdict RULE: 'fail' if ANY HIGH-risk unit is UNSUPPORTED or CONTRADICTED, else 'pass'."
)


# ── DB helpers ───────────────────────────────────────────────────────────────
async def _rows(db, sql: str, sid: str) -> list[dict]:
    res = await db.execute(text(sql), {"sid": sid})
    return [dict(r._mapping) for r in res.fetchall()]


async def _row(db, sql: str, sid: str) -> dict | None:
    res = await db.execute(text(sql), {"sid": sid})
    r = res.first()
    return dict(r._mapping) if r is not None else None


async def load_ledger(db, sid: str) -> dict:
    cluster = await _row(db, """
        SELECT representative_title, topic, event_type, subject_country,
               article_count, source_count, independent_source_count,
               primary_entities, languages,
               to_char(first_seen_at,'YYYY-MM-DD') AS first_day,
               to_char(last_seen_at,'YYYY-MM-DD')  AS last_day
          FROM analytics.story_clusters_v8 WHERE story_id = :sid
    """, sid)
    facts = await _rows(db, """
        SELECT fact_key, unit, value_min, value_max, value_latest, member_count,
               single_source, sample_claim,
               COALESCE(array_length(citing_article_ids,1),0) AS n_cite
          FROM analytics.story_facts_v8 WHERE story_id = :sid
         ORDER BY member_count DESC NULLS LAST, n_cite DESC LIMIT 45
    """, sid)
    quotes = await _rows(db, """
        SELECT COALESCE(quote_text_en, quote_text) AS quote_text_en, speaker, is_direct
          FROM analytics.story_quotes_v8
         WHERE story_id = :sid
           AND COALESCE(quote_text_en, quote_text) IS NOT NULL
           AND length(COALESCE(quote_text_en, quote_text)) > 15
         ORDER BY is_direct DESC, length(COALESCE(quote_text_en, quote_text)) DESC LIMIT 18
    """, sid)
    timeline = await _row(db, """
        SELECT to_char(first_seen_at,'YYYY-MM-DD HH24:MI') AS first_at,
               to_char(last_seen_at,'YYYY-MM-DD HH24:MI')  AS last_at,
               to_char(peak_at,'YYYY-MM-DD HH24:MI')       AS peak_at,
               velocity, span_hours, is_breaking
          FROM analytics.story_timeline_v8 WHERE story_id = :sid
    """, sid)
    geo = await _row(db, """
        SELECT primary_country, continent, country_spread
          FROM analytics.story_geo_v8 WHERE story_id = :sid
    """, sid)
    stance = await _row(db, """
        SELECT stance_distribution, sentiment, n_stances
          FROM analytics.story_stance_v8 WHERE story_id = :sid
    """, sid)
    sources = await _rows(db, """
        SELECT source_tier, COUNT(*) AS n, SUM(articles_from_source) AS arts
          FROM analytics.story_sources_v8 WHERE story_id = :sid
         GROUP BY source_tier ORDER BY arts DESC NULLS LAST
    """, sid)
    return dict(sid=sid, cluster=cluster or {}, facts=facts, quotes=quotes,
                timeline=timeline or {}, geo=geo or {}, stance=stance or {}, sources=sources)


def _ents(val) -> str:
    if not val:
        return ""
    try:
        data = val if isinstance(val, (list, dict)) else json.loads(val)
    except Exception:
        return str(val)[:200]
    names = []
    if isinstance(data, list):
        for e in data[:12]:
            if isinstance(e, dict):
                names.append(str(e.get("name") or e.get("text") or e.get("entity") or e))
            else:
                names.append(str(e))
    elif isinstance(data, dict):
        names = [str(k) for k in list(data.keys())[:12]]
    return ", ".join(n for n in names if n)


def _num(f: dict) -> str:
    mn, mx, lt, unit = f.get("value_min"), f.get("value_max"), f.get("value_latest"), f.get("unit") or ""
    if mn is None and mx is None and lt is None:
        return ""
    if mn is not None and mx is not None and str(mn) != str(mx):
        return f" [RANGE {mn}-{mx} {unit}]".rstrip()
    v = lt if lt is not None else (mn if mn is not None else mx)
    return f" [{v} {unit}]".rstrip()


def ledger_to_text(L: dict) -> str:
    c = L["cluster"]
    out = []
    out.append("=== STORY ANCHOR ===")
    out.append(f"Working title (source-derived, may be tabloid): {c.get('representative_title','')}")
    out.append(f"Topic: {c.get('topic','')}   Event type: {c.get('event_type','')}")
    out.append(f"Subject country: {c.get('subject_country','')}   "
               f"Geo: {L['geo'].get('primary_country','')}/{L['geo'].get('continent','')} "
               f"(spread {L['geo'].get('country_spread','')})")
    out.append(f"Coverage: {c.get('article_count','?')} articles from "
               f"{c.get('independent_source_count','?')} independent sources "
               f"({c.get('first_day','?')} -> {c.get('last_day','?')})")
    ents = _ents(c.get("primary_entities"))
    if ents:
        out.append(f"Key entities: {ents}")
    tl = L["timeline"]
    if tl:
        out.append(f"Timeline: first {tl.get('first_at','?')}, peak {tl.get('peak_at','?')}, "
                   f"last {tl.get('last_at','?')}, breaking={tl.get('is_breaking')}")
    st = L["stance"]
    if st and st.get("stance_distribution"):
        out.append(f"Stance distribution: {json.dumps(st.get('stance_distribution'))[:300]}")

    out.append("\n=== FACTS (deduped, multi-source; member_count = corroborating members) ===")
    for i, f in enumerate(L["facts"], 1):
        ss = "  (SINGLE-SOURCE)" if f.get("single_source") else ""
        claim = (f.get("sample_claim") or f.get("fact_key") or "").strip().replace("\n", " ")
        out.append(f"{i}. {claim}{_num(f)}  <members={f.get('member_count')}, cites={f.get('n_cite')}>{ss}")
    if not L["facts"]:
        out.append("(none)")

    out.append("\n=== QUOTES (verbatim, English; attribute exactly) ===")
    for i, q in enumerate(L["quotes"], 1):
        kind = "direct" if q.get("is_direct") else "indirect"
        sp = (q.get("speaker") or "unknown speaker").strip()
        out.append(f'{i}. {sp} ({kind}): "{(q.get("quote_text_en") or "").strip()}"')
    if not L["quotes"]:
        out.append("(none)")

    srcs = ", ".join(f"{s.get('source_tier') or 'untiered'}:{s.get('n')}" for s in L["sources"])
    out.append(f"\n=== SOURCE TIERS === {srcs}")
    return "\n".join(out)


# ── LLM wrappers ─────────────────────────────────────────────────────────────
async def _llm(system: str, user: str, *, model: str, json_mode: bool, max_tokens: int,
               temperature: float | None = None) -> str:
    return await asyncio.wait_for(
        call_groq(system=system, user=user, task_type="generation", model=model,
                  json_response=json_mode, max_tokens_override=max_tokens,
                  temperature_override=temperature),
        timeout=CALL_TIMEOUT,
    )


def _parse_json(raw: str) -> dict:
    t = raw.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{"):] if "{" in t else t
    a, b = t.find("{"), t.rfind("}")
    if a >= 0 and b > a:
        t = t[a:b + 1]
    return json.loads(t)


def parse_article(raw: str) -> tuple[str, str, str]:
    t = (raw or "").strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
    headline = deck = ""
    m = re.search(r"HEADLINE:\s*(.+)", t)
    if m:
        headline = m.group(1).strip()
    m = re.search(r"DECK:\s*(.+)", t)
    if m:
        deck = m.group(1).strip()
    if "\n---" in t:
        body = t.split("\n---", 1)[1].lstrip("-\n ").strip()
    elif "---" in t:
        body = t.split("---", 1)[1].lstrip("-\n ").strip()
    else:
        body = re.sub(r"^(HEADLINE|DECK):.*$", "", t, flags=re.M).strip()
    return headline, deck, body


async def guard_c(ledger_text: str) -> dict:
    raw = await _llm(SYS_GUARD_C, ledger_text, model=VERIFY_MODEL, json_mode=True, max_tokens=1500, temperature=0.0)
    try:
        return _parse_json(raw)
    except Exception as exc:
        return {"verdict": "ERROR", "dominant": "", "others": [], "error": str(exc)[:160]}


async def verify(headline: str, body: str, ledger_text: str) -> dict:
    user = f"SOURCE FACT-LEDGER:\n{ledger_text}\n\n=== ARTICLE ===\nHEADLINE: {headline}\n\n{body}"
    raw = await _llm(SYS_VERIFY, user, model=VERIFY_MODEL, json_mode=True, max_tokens=3200, temperature=0.0)
    try:
        data = _parse_json(raw)
    except Exception as exc:
        return {"verdict": "fail", "units": [], "error": f"verifier-parse: {str(exc)[:160]}",
                "failing": [], "computed_verdict": "fail"}
    units = data.get("units") or []
    failing = [u for u in units
               if str(u.get("risk", "")).upper() == "HIGH"
               and str(u.get("status", "")).upper() in ("UNSUPPORTED", "CONTRADICTED")]
    data["failing"] = failing
    data["computed_verdict"] = "fail" if failing else "pass"
    return data


async def verify_voted(headline: str, body: str, ledger_text: str) -> dict:
    """Deterministic (temp 0) faithfulness check with 2-of-3 majority at the boundary:
    reject ONLY if >=2 of 3 passes FAIL. Keeps the strict HIGH-risk bar; removes the
    run-to-run flip noise. Short-circuits once >=2 agree (usually 2 calls, max 3)."""
    results: list[dict] = []
    for _ in range(3):
        results.append(await verify(headline, body, ledger_text))
        n_fail = sum(1 for r in results if r.get("computed_verdict") == "fail")
        n_pass = sum(1 for r in results if r.get("computed_verdict") == "pass")
        if n_pass >= 2 or n_fail >= 2:
            break
    n_fail = sum(1 for r in results if r.get("computed_verdict") == "fail")
    verdict = "fail" if n_fail >= 2 else "pass"
    rep = dict(next((r for r in results if r.get("computed_verdict") == verdict), results[-1]))
    rep["computed_verdict"] = verdict
    rep["votes"] = [r.get("computed_verdict") for r in results]
    return rep


async def generate(system: str, ledger_text: str) -> tuple[str, str, str, str]:
    raw = await _llm(system, ledger_text, model=GEN_MODEL, json_mode=False, max_tokens=GEN_TOKENS)
    h, d, b = parse_article(raw)
    return h, d, b, raw


# ── Per-story pipeline ───────────────────────────────────────────────────────
async def run_story(L: dict) -> dict:
    sid = L["sid"]
    ltext = ledger_to_text(L)
    title = L["cluster"].get("representative_title", "")
    print(f"\n{'='*70}\nSTORY {sid}\n  {title[:90]}\n  facts={len(L['facts'])} quotes={len(L['quotes'])} "
          f"arts={L['cluster'].get('article_count')}", flush=True)

    gc = await guard_c(ltext)
    print(f"  Guard C: {gc.get('verdict')}  dominant={str(gc.get('dominant',''))[:80]}", flush=True)

    attempts = []
    chosen = None
    # Hybrid A, up to MAX_A_TRIES
    for t in range(1, MAX_A_TRIES + 1):
        h, d, b, raw = await generate(SYS_HYBRID_A, ltext)
        wc = len(b.split())
        if not b.strip():
            attempts.append({"strategy": f"A{t}", "verdict": "fail", "reason": "empty content", "words": 0})
            print(f"  A try{t}: EMPTY content (reasoning ate budget?)", flush=True)
            continue
        v = await verify_voted(h, b, ltext)
        ok = v.get("computed_verdict") == "pass"
        attempts.append({"strategy": f"A{t}", "verdict": v.get("computed_verdict"),
                         "words": wc, "n_units": len(v.get("units") or []),
                         "n_fail": len(v.get("failing") or [])})
        print(f"  A try{t}: {wc}w  verify={v.get('computed_verdict')} "
              f"(units={len(v.get('units') or [])}, HIGH-fail={len(v.get('failing') or [])})", flush=True)
        if ok:
            chosen = {"strategy": f"Hybrid A (try {t})", "headline": h, "deck": d, "body": b,
                      "words": wc, "verify": v}
            break
    # Hybrid B fallback
    if chosen is None:
        h, d, b, raw = await generate(SYS_HYBRID_B, ltext)
        wc = len(b.split())
        v = await verify_voted(h, b, ltext) if b.strip() else {"computed_verdict": "fail", "units": [], "failing": []}
        attempts.append({"strategy": "B", "verdict": v.get("computed_verdict"), "words": wc,
                         "n_units": len(v.get("units") or []), "n_fail": len(v.get("failing") or [])})
        print(f"  B fallback: {wc}w  verify={v.get('computed_verdict')}", flush=True)
        if v.get("computed_verdict") == "pass":
            chosen = {"strategy": "Hybrid B (fallback)", "headline": h, "deck": d, "body": b,
                      "words": wc, "verify": v}

    status = "PUBLISHABLE" if chosen else "EXTRACTIVE-FALLBACK (all gens failed verify)"
    if gc.get("verdict") == "SEVERAL":
        status += " | HELD (Guard C: multi-event — needs _v8 split)"

    return {"sid": sid, "title": title, "ledger_text": ltext, "guard_c": gc,
            "attempts": attempts, "chosen": chosen, "status": status}


def write_outputs(results: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = ["# Worldwide content-gen — first sample run\n",
               f"Model (prose): `{GEN_MODEL}`  ·  Verifier/Guard-C: `{VERIFY_MODEL}`\n",
               "Verdict = faithfulness of the ARTICLE against its own fact-ledger "
               "(did generation stay inside its inputs).\n"]
    for i, r in enumerate(results, 1):
        ch = r["chosen"]
        summary.append(f"\n## {i}. {r['title'][:90]}")
        summary.append(f"- **Status:** {r['status']}")
        summary.append(f"- **Guard C:** {r['guard_c'].get('verdict')} "
                       f"— dominant: {str(r['guard_c'].get('dominant',''))[:120]}")
        summary.append(f"- **Attempts:** {r['attempts']}")
        if ch:
            summary.append(f"- **Won with:** {ch['strategy']} · {ch['words']} words")
            summary.append(f"- **Headline:** {ch['headline']}")
            summary.append(f"- **Deck:** {ch['deck']}")
        # per-story full file
        fn = OUT_DIR / f"{i:02d}_{r['sid'][:8]}.md"
        lines = [f"# {(ch['headline'] if ch else r['title'])}\n"]
        if ch:
            lines += [f"*{ch['deck']}*\n", f"`{ch['strategy']} · {ch['words']} words · "
                      f"verify={ch['verify'].get('computed_verdict')}`\n", "---\n", ch["body"], "\n"]
            fails = ch["verify"].get("failing") or []
            if fails:
                lines.append("\n## Verifier — HIGH-risk units that failed\n")
                for u in fails:
                    lines.append(f"- [{u.get('status')}] {u.get('text')}")
        else:
            lines.append("\n**No publishable draft** — all generations failed the faithfulness gate; "
                         "recipe says fall back to extractive summary here.\n")
        lines.append("\n\n---\n## Fact-ledger used\n\n```\n" + r["ledger_text"] + "\n```\n")
        fn.write_text("\n".join(lines), encoding="utf-8")
    (OUT_DIR / "SUMMARY.md").write_text("\n".join(summary), encoding="utf-8")
    print(f"\nWrote {len(results)} articles + SUMMARY.md to {OUT_DIR}", flush=True)


async def main() -> int:
    ids = sys.argv[1:] or DEFAULT_STORY_IDS
    print(f"Loading ledgers for {len(ids)} stories…", flush=True)
    async with get_db() as db:
        ledgers = [await load_ledger(db, sid) for sid in ids]
    results = []
    for L in ledgers:
        try:
            results.append(await run_story(L))
        except Exception as exc:
            print(f"  !! story {L['sid']} errored: {str(exc)[:200]}", flush=True)
            results.append({"sid": L["sid"], "title": L["cluster"].get("representative_title", ""),
                            "ledger_text": ledger_to_text(L), "guard_c": {"verdict": "ERROR"},
                            "attempts": [], "chosen": None, "status": f"ERROR: {str(exc)[:120]}"})
    write_outputs(results)
    print("\n===== CONSOLE SUMMARY =====", flush=True)
    for i, r in enumerate(results, 1):
        print(f"{i}. {r['status']:<55} | {r['title'][:60]}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
