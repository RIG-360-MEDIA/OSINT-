"""_gen_source_hardened.py — B1: production-hardened source-grounded generator.

Three upgrades over the _gen_source_ab prototype:
  1. INDEPENDENT verifier — a different model family from the writer (writer=qwen local,
     verifier=llama-3.3-70b Meta), so faithfulness isn't self-graded.
  2. CITE-ID provenance — the verifier attributes every HARD fact to the SOURCE number(s)
     that support it → a {fact -> [source]} map suitable for story_generated_v8.claim_provenance.
  3. PER-BAND length policy — target scales with cluster coverage; thin clusters stay short
     (no padding), rich clusters earn length.

READ-ONLY on the DB. Writes article+provenance files to /app/scripts/_gen_hard_out.
Run:  docker exec rig-backend python /app/scripts/_gen_source_hardened.py [story_ids...]
Env:  GEN_MODEL(qwen2.5:32b) VERIFY_MODEL(llama-3.3-70b-versatile) GEN_TOKENS(4500)
"""
from __future__ import annotations

import asyncio, json, os, sys
from pathlib import Path

sys.path.insert(0, "/app"); sys.path.insert(0, "/app/scripts")
from sqlalchemy import text  # noqa: E402
from backend.database import get_db  # noqa: E402
import _worldwide_gen_sample as base  # noqa: E402
from _worldwide_gen_sample import load_ledger, ledger_to_text, parse_article  # noqa: E402
from _gen_source_ab import load_sources, sources_to_text, copy_overlap, SAMPLE_SQL  # noqa: E402

GEN_MODEL = os.getenv("GEN_MODEL", "qwen2.5:32b")               # writer (local, unlimited)
VERIFY_MODEL = os.getenv("VERIFY_MODEL", "llama-3.3-70b-versatile")  # INDEPENDENT family (Meta)
GEN_TOKENS = int(os.getenv("GEN_TOKENS", "4500"))
OUT_DIR = Path(os.getenv("HARD_OUT", "/app/scripts/_gen_hard_out"))


def band_of(src_words: int) -> tuple[str, int, int]:
    """Per-band length target (lo, hi) — keyed off ACTUAL source material fed (total words),
    so thin clusters stay short (no padding) and richly-sourced ones earn length. Using real
    material (not a possibly-stale source_count) is what prevents over-writing thin clusters."""
    if src_words < 1500:
        return ("small", 250, 500)
    if src_words < 5000:
        return ("medium", 450, 850)
    return ("large", 750, 1200)


def sys_gen(lo: int, hi: int) -> str:
    return (
        "You are a senior staff writer and analyst for a flagship intelligence-grade publication "
        "(an Atlantic long-read with a Reuters wire desk's rigour). You are given (1) numbered SOURCE "
        "REPORTS from MULTIPLE INDEPENDENT outlets on the SAME event and (2) a VERIFIED FACT-LEDGER. "
        "Write ONE rich, authoritative article that SYNTHESISES all the source reporting.\n\n"
        f"LENGTH: aim for {lo}-{hi} words. This target reflects how well-covered the event is. If the "
        f"material genuinely does not support {lo} words, write less and stop — NEVER pad, repeat, or "
        "invent connective detail to hit a number. Length must follow real information.\n\n"
        "STRUCTURE (adapt): sharp lede; key facts/figures; how it unfolded; what people said (quotes, "
        "attributed); context & background; reactions/competing perspectives; significance / what's next "
        "(your analytical lane).\n\n"
        "FAITHFULNESS (intelligence product — fabrication is fatal):\n"
        "  - HARD FACTS (every number, named quote, date, specific claim about a named person/org) MUST "
        "come from the SOURCES or LEDGER. Never invent, inflate, round, or reassign. If sources disagree "
        "on a figure, give the RANGE and note it.\n"
        "  - You MAY write connective narrative, context and significance in your own words, but such "
        "prose must NOT assert any NEW checkable fact the sources don't support. Analysis reads as analysis.\n"
        "  - Attribute contested/single-source claims ('according to <outlet>'). ONE event only.\n"
        "  - Fresh original headline + deck; do not copy a source headline or lift sentences verbatim.\n\n"
        "OUTPUT EXACTLY:\n"
        "HEADLINE: <fresh headline, <=16 words>\n"
        "DECK: <one-sentence summary, <=35 words>\n"
        "---\n"
        "<the article body as flowing prose paragraphs>"
    )


SYS_VERIFY_ATTR = (
    "You are a strict FAITHFULNESS checker AND source attributor. You are given numbered SOURCE REPORTS, "
    "a FACT-LEDGER (corroborated quotes/facts distilled from the WHOLE cluster — also authoritative), and "
    "an ARTICLE. For EVERY checkable unit in the article — every number, every quote, every claim about a "
    "named person/organisation — decide whether it is SUPPORTED, CONTRADICTED, or UNSUPPORTED. A unit is "
    "SUPPORTED if it appears in EITHER the SOURCE REPORTS OR the FACT-LEDGER. Judge ONLY against these two, "
    "never your own knowledge. For each SUPPORTED unit, list the SOURCE NUMBERS that support it (use an empty "
    "list [] if it is supported only by the ledger).\n"
    "Risk tiers: HIGH = numbers, quotes, claims about named living people/orgs. MED = paraphrase/summary. "
    "LOW = framing/topic.\n"
    "Return STRICT JSON, no prose, no fences:\n"
    '{"units":[{"text":"<unit, <=160 chars>","type":"number|quote|claim|entity","risk":"HIGH|MED|LOW",'
    '"status":"SUPPORTED|CONTRADICTED|UNSUPPORTED","sources":[<source numbers>]}],"verdict":"pass|fail"}\n'
    "verdict RULE: 'fail' if ANY HIGH-risk unit is CONTRADICTED, or if any HIGH-risk number/quote is "
    "UNSUPPORTED. Otherwise 'pass'."
)


async def verify_attr(headline: str, body: str, stext: str, ltext: str) -> dict:
    user = (f"SOURCE REPORTS:\n{stext}\n\n=== FACT-LEDGER (also authoritative) ===\n{ltext}\n\n"
            f"=== ARTICLE ===\nHEADLINE: {headline}\n\n{body}")
    raw = await base._llm(SYS_VERIFY_ATTR, user, model=VERIFY_MODEL, json_mode=True, max_tokens=4000, temperature=0.0)
    try:
        data = base._parse_json(raw)
    except Exception as exc:
        return {"units": [], "verdict": "fail", "error": f"verifier-parse: {str(exc)[:120]}"}
    units = data.get("units") or []
    hi = [u for u in units if str(u.get("risk", "")).upper() == "HIGH"]
    sup = [u for u in hi if str(u.get("status", "")).upper() == "SUPPORTED"]
    contra = [u for u in hi if str(u.get("status", "")).upper() == "CONTRADICTED"]
    unsup = [u for u in hi if str(u.get("status", "")).upper() == "UNSUPPORTED"]
    provenance = [{"fact": u.get("text"), "type": u.get("type"), "sources": u.get("sources") or []}
                  for u in sup]
    return {
        "units": units, "n_units": len(units), "n_high": len(hi),
        "hard_faith": round(100 * len(sup) / max(len(hi), 1)),
        "contra": len(contra), "unsup": len(unsup),
        "verdict": "fail" if (contra or unsup) else "pass",
        "provenance": provenance,
        "provenance_coverage": round(100 * sum(1 for p in provenance if p["sources"]) / max(len(sup), 1)),
    }


async def generate_hardened(L: dict, srcs: list[dict]) -> dict:
    src_words = sum(len((s.get("body") or "").split()) for s in srcs)
    band, lo, hi = band_of(src_words)
    stext = sources_to_text(srcs)
    ltext = ledger_to_text(L)
    user = (f"SOURCE REPORTS (independent outlets on the SAME event):\n\n{stext}\n\n"
            f"=== VERIFIED FACT-LEDGER ===\n{ltext}")
    raw = await base._llm(sys_gen(lo, hi), user, model=GEN_MODEL, json_mode=False, max_tokens=GEN_TOKENS)
    h, d, b = parse_article(raw)
    wc = len(b.split())
    v = await verify_attr(h, b, stext, ltext) if b.strip() else {"hard_faith": 0, "contra": 0, "verdict": "fail",
                                                          "provenance": [], "n_high": 0, "provenance_coverage": 0}
    return {"band": band, "target": f"{lo}-{hi}", "headline": h, "deck": d, "body": b, "words": wc,
            "n_sources": len(srcs), "overlap": copy_overlap(b, srcs),
            "writer": GEN_MODEL, "verifier": VERIFY_MODEL, **v}


def write_story(idx: int, sid: str, L: dict, srcs: list[dict], r: dict) -> None:
    fn = OUT_DIR / f"{idx:02d}_{r['band']}_{sid[:8]}.md"
    prov = "\n".join(f"- [{','.join('S'+str(s) for s in p['sources'])}] {p['fact']}"
                     for p in r.get("provenance", [])) or "(none)"
    fails = [u for u in r.get("units", [])
             if str(u.get("status", "")).upper() in ("UNSUPPORTED", "CONTRADICTED")
             and str(u.get("risk", "")).upper() == "HIGH"]
    audit = "\n".join(f"- [{u.get('status')}] {u.get('text')}" for u in fails) or "(none)"
    srcsnips = "\n\n".join(f"[S{i}] {(s.get('title') or '')[:90]}\n{((s.get('body') or '')[:280])}"
                           for i, s in enumerate(srcs, 1))
    lines = [f"# {r['headline']}", f"*{r['deck']}*\n",
             f"`band={r['band']} target={r['target']}w · {r['words']}w · writer={r['writer']} · "
             f"verifier={r['verifier']} (INDEPENDENT)`",
             f"`hard-faith {r['hard_faith']}% (HIGH {r['n_high']}, contra {r['contra']}, unsup {r.get('unsup',0)}) · "
             f"verdict={r['verdict']} · provenance-coverage {r.get('provenance_coverage',0)}% · overlap {r['overlap']}`\n",
             "---\n", r["body"], "\n",
             "\n## Cite-ID provenance (hard facts → source #)\n", prov, "\n",
             "\n## HIGH-risk units the INDEPENDENT verifier flagged (audit)\n", audit, "\n",
             "\n## Source snippets (for spot-check)\n", srcsnips, "\n",
             "\n---\n## Fact-ledger\n```\n" + ledger_to_text(L) + "\n```\n"]
    fn.write_text("\n".join(lines), encoding="utf-8")


async def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    async with get_db() as db:
        if len(sys.argv) > 1:
            rows = [{"story_id": a, "band": "?"} for a in sys.argv[1:]]
        else:
            res = await db.execute(text(SAMPLE_SQL))
            rows = [dict(r._mapping) for r in res.fetchall()]
        print(f"B1 hardened gen on {len(rows)} stories (writer={GEN_MODEL}, verifier={VERIFY_MODEL})\n", flush=True)
        summary = []
        for idx, row in enumerate(rows, 1):
            sid = row["story_id"]
            L = await load_ledger(db, sid)
            srcs = await load_sources(db, sid)
            try:
                r = await generate_hardened(L, srcs)
            except Exception as exc:
                print(f"[{idx}] {sid[:8]} ERROR {str(exc)[:140]}", flush=True)
                continue
            write_story(idx, sid, L, srcs, r)
            summary.append({"sid": sid[:8], "band": r["band"], "target": r["target"], "words": r["words"],
                            "hard_faith": r["hard_faith"], "contra": r["contra"], "verdict": r["verdict"],
                            "prov_cov": r.get("provenance_coverage", 0), "overlap": r["overlap"]})
            print(f"[{idx}] {r['band']:<6} {sid[:8]} target={r['target']:<9} {r['words']:>4}w  "
                  f"faith={r['hard_faith']}% contra={r['contra']} verdict={r['verdict']} "
                  f"prov-cov={r.get('provenance_coverage',0)}% overlap={r['overlap']}", flush=True)
        (OUT_DIR / "_metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\nWrote {len(summary)} hardened articles + provenance to {OUT_DIR}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
