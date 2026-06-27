"""_gen_source_ab.py — A/B prototype: SOURCE-GROUNDED long-form vs the LEDGER generator.

Reuses _worldwide_gen_sample for the LEDGER side (identical plumbing → clean A/B). Adds a
SOURCE-GROUNDED path that feeds the model the actual member-article FULL TEXTS + the ledger,
pushes length/creativity, and verifies HARD facts against the SOURCE SET (two-class faithfulness:
hard facts strict, soft prose lenient). Writes side-by-side comparison files + a metrics summary.

READ-ONLY on the DB — writes NOTHING to story_generated_v8. Pure evaluation harness.

Run inside the backend container:
    docker exec rig-backend python /app/scripts/_gen_source_ab.py
Optional: pass story_ids as args to override the auto band-sample.
Env: AB_MAX_SOURCES(10) AB_SRC_CHARS(1800) AB_GEN_TOKENS(5200) AB_VOTE(0) WW_GEN_MODEL WW_VERIFY_MODEL
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/scripts")

from sqlalchemy import text  # noqa: E402

from backend.database import get_db  # noqa: E402

import _worldwide_gen_sample as base  # noqa: E402
from _worldwide_gen_sample import (  # noqa: E402
    GEN_MODEL, ledger_to_text, load_ledger, parse_article,
)

OUT_DIR = Path(os.getenv("AB_OUT", "/app/scripts/_gen_ab_out"))
MAX_SOURCES = int(os.getenv("AB_MAX_SOURCES", "10"))
SRC_CHARS = int(os.getenv("AB_SRC_CHARS", "1800"))
GEN_TOKENS = int(os.getenv("AB_GEN_TOKENS", "5200"))
VOTE = os.getenv("AB_VOTE", "0") == "1"

# ── The source-grounded prose prompt: BIG + creative, hard/soft faithfulness split ──
SYS_SOURCE_A = (
    "You are a senior staff writer and analyst for a flagship intelligence-grade publication "
    "(think a long-read in The Atlantic, with the rigour of a Reuters wire desk). You are given "
    "(1) SOURCE REPORTS — excerpts from MULTIPLE INDEPENDENT outlets all covering the SAME event — "
    "and (2) a VERIFIED FACT-LEDGER distilled from them. Write ONE rich, authoritative, in-depth "
    "article that SYNTHESISES all the source reporting into a single coherent account.\n\n"
    "LENGTH & DEPTH — write the FULLEST article the material genuinely supports. A well-covered "
    "event should run 700-1100+ words. Mine every distinct angle, detail, figure, quote, reaction "
    "and consequence across the sources; use the breadth to add sequence, context and significance. "
    "Do NOT pad with empty phrasing — but do NOT leave real material on the table either.\n\n"
    "STRUCTURE (adapt to the story, use what fits):\n"
    "  - a sharp lede capturing the core development;\n"
    "  - the key facts and figures;\n"
    "  - how it unfolded (chronology / sequence);\n"
    "  - what people said (quotes, attributed);\n"
    "  - context & background (what led here, prior related events);\n"
    "  - reactions and competing perspectives across the sources;\n"
    "  - significance — what it means and what comes next (this is your analytical lane).\n\n"
    "FAITHFULNESS DISCIPLINE (this is an intelligence product — fabrication is fatal):\n"
    "  - HARD FACTS — every number, named quote, date, and specific claim about a named person or "
    "organisation — MUST come from the SOURCES or the LEDGER. Never invent, inflate, round, or "
    "reassign them. If sources disagree on a figure, give the RANGE and note the disagreement.\n"
    "  - You MAY write connective narrative, context, framing and significance in your OWN words "
    "(that is the writer's craft) — but such prose must NOT assert any NEW checkable fact the "
    "sources do not support. Analysis must read as analysis, not as new reporting.\n"
    "  - Attribute contested or single-source claims ('according to <outlet>', '<X> said'). "
    "Distinguish what is confirmed across sources from what one outlet reports.\n"
    "  - ONE EVENT ONLY. If the material mixes unrelated events, write the single dominant one.\n"
    "  - Write a FRESH, original headline and deck. Do NOT copy a source headline, and do NOT lift "
    "whole sentences verbatim from any single source — synthesise in your own words.\n\n"
    "VOICE: authoritative, precise, narratively engaging — a flagship publication's signature "
    "analysis, neither a dry bullet summary nor breathless tabloid.\n\n"
    "OUTPUT EXACTLY this shape and nothing else:\n"
    "HEADLINE: <fresh, neutral, accurate headline, <=16 words>\n"
    "DECK: <one-sentence summary, <=35 words>\n"
    "---\n"
    "<the article body as flowing prose paragraphs>"
)

SOURCE_SQL = """
SELECT title, body, source_name, day, blen FROM (
  SELECT DISTINCT ON (a.source_id)
    COALESCE(a.title,'') AS title,
    COALESCE(a.full_text_translated, a.full_text_scraped,
             a.lead_text_translated, a.lead_text_original, '') AS body,
    COALESCE(s.name, s.domain, 'unknown') AS source_name,
    to_char(a.published_at,'YYYY-MM-DD') AS day,
    length(COALESCE(a.full_text_translated, a.full_text_scraped,
                    a.lead_text_translated, a.lead_text_original, '')) AS blen
  FROM analytics.story_cluster_members_v8 m
  JOIN articles a ON a.id = m.article_id
  LEFT JOIN sources s ON s.id = a.source_id
  WHERE m.story_id = :sid
    AND COALESCE(a.full_text_translated, a.full_text_scraped,
                 a.lead_text_translated, a.lead_text_original, '') <> ''
  ORDER BY a.source_id, blen DESC
) x ORDER BY blen DESC LIMIT :lim
"""

SAMPLE_SQL = """
(SELECT story_id::text, article_count, 'small' band FROM analytics.story_clusters_v8 c
   WHERE article_count BETWEEN 2 AND 5 AND independent_source_count >= 3
     AND EXISTS (SELECT 1 FROM analytics.story_facts_v8 f WHERE f.story_id=c.story_id)
   ORDER BY independent_source_count DESC, article_count DESC LIMIT 3)
UNION ALL
(SELECT story_id::text, article_count, 'medium' band FROM analytics.story_clusters_v8 c
   WHERE article_count BETWEEN 6 AND 20 AND independent_source_count >= 3
     AND EXISTS (SELECT 1 FROM analytics.story_facts_v8 f WHERE f.story_id=c.story_id)
   ORDER BY independent_source_count DESC, article_count DESC LIMIT 3)
UNION ALL
(SELECT story_id::text, article_count, 'large' band FROM analytics.story_clusters_v8 c
   WHERE article_count >= 21 AND independent_source_count >= 3
     AND EXISTS (SELECT 1 FROM analytics.story_facts_v8 f WHERE f.story_id=c.story_id)
   ORDER BY independent_source_count DESC, article_count DESC LIMIT 3)
"""


async def load_sources(db, sid: str) -> list[dict]:
    res = await db.execute(text(SOURCE_SQL), {"sid": sid, "lim": MAX_SOURCES})
    return [dict(r._mapping) for r in res.fetchall()]


def sources_to_text(srcs: list[dict]) -> str:
    out = []
    for i, s in enumerate(srcs, 1):
        body = (s.get("body") or "").strip().replace("\r", " ")
        if len(body) > SRC_CHARS:
            body = body[:SRC_CHARS].rsplit(" ", 1)[0] + " …"
        out.append(f"[SOURCE {i} — {s.get('source_name','?')}, {s.get('day','?')}]\n"
                   f"HEADLINE: {s.get('title','')}\n{body}")
    return "\n\n".join(out)


def copy_overlap(body: str, srcs: list[dict], n: int = 8) -> float:
    """Max fraction of the article's n-grams that appear verbatim in ANY single source
    (plagiarism / copy-paste signal — we want this LOW = genuine synthesis)."""
    def grams(t: str) -> set:
        w = re.findall(r"\w+", (t or "").lower())
        return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)} if len(w) >= n else set()
    bg = grams(body)
    if not bg:
        return 0.0
    best = 0.0
    for s in srcs:
        sg = grams(s.get("body") or "")
        if sg:
            best = max(best, len(bg & sg) / len(bg))
    return round(best, 3)


def faith(v: dict | None) -> dict:
    """Hard-unit faithfulness from a verifier result (HIGH-risk units only)."""
    units = (v or {}).get("units") or []
    hi = [u for u in units if str(u.get("risk", "")).upper() == "HIGH"]
    sup = [u for u in hi if str(u.get("status", "")).upper() == "SUPPORTED"]
    contra = [u for u in hi if str(u.get("status", "")).upper() == "CONTRADICTED"]
    unsup = [u for u in hi if str(u.get("status", "")).upper() == "UNSUPPORTED"]
    return {"hi": len(hi), "sup": len(sup), "contra": len(contra), "unsup": len(unsup),
            "hard_faith": round(100 * len(sup) / max(len(hi), 1)),
            "total_units": len(units)}


async def _verify(headline: str, body: str, oracle: str) -> dict:
    return await (base.verify_voted(headline, body, oracle) if VOTE
                  else base.verify(headline, body, oracle))


async def run_ledger(L: dict) -> dict:
    """LEDGER side: one Hybrid-A gen verified against the ledger (symmetric to source side)."""
    ltext = ledger_to_text(L)
    h, d, b, _ = await base.generate(base.SYS_HYBRID_A, ltext)
    wc = len(b.split())
    v = await _verify(h, b, ltext) if b.strip() else None
    return {"mode": "ledger", "headline": h, "deck": d, "body": b, "words": wc,
            "verify": v, "overlap": None, "faith": faith(v)}


async def run_source(L: dict, srcs: list[dict]) -> dict:
    """SOURCE side: one long-form gen from full source texts, verified against sources+ledger."""
    ltext = ledger_to_text(L)
    stext = sources_to_text(srcs)
    oracle = f"=== SOURCE REPORTS ===\n{stext}\n\n=== FACT-LEDGER ===\n{ltext}"
    user = (f"SOURCE REPORTS (independent outlets on the SAME event):\n\n{stext}\n\n"
            f"=== VERIFIED FACT-LEDGER (corroborated facts/numbers/quotes) ===\n{ltext}")
    raw = await base._llm(SYS_SOURCE_A, user, model=GEN_MODEL, json_mode=False, max_tokens=GEN_TOKENS)
    h, d, b = parse_article(raw)
    wc = len(b.split())
    v = await _verify(h, b, oracle) if b.strip() else None
    return {"mode": "source", "headline": h, "deck": d, "body": b, "words": wc,
            "verify": v, "overlap": copy_overlap(b, srcs), "faith": faith(v),
            "n_sources": len(srcs),
            "src_words": sum(len((s.get("body") or "").split()) for s in srcs)}


def write_story(idx: int, sid: str, band: str, L: dict, srcs: list[dict],
                led: dict, src: dict) -> None:
    fn = OUT_DIR / f"{idx:02d}_{band}_{sid[:8]}.md"
    title = L["cluster"].get("representative_title", "")
    lines = [f"# A/B — {title[:90]}", f"`band={band}  story={sid}  sources_fed={src.get('n_sources')}  "
             f"source_material≈{src.get('src_words')}w`\n",
             "## ▶ SOURCE-GROUNDED (new)",
             f"`{src['words']} words · hard-faith {src['faith']['hard_faith']}% "
             f"(HIGH {src['faith']['sup']}/{src['faith']['hi']}, contra {src['faith']['contra']}) · "
             f"copy-overlap {src['overlap']}`\n",
             f"### {src['headline']}", f"*{src['deck']}*\n", src["body"], "\n",
             "## ▶ LEDGER (current)",
             f"`{led['words']} words · hard-faith {led['faith']['hard_faith']}% "
             f"(HIGH {led['faith']['sup']}/{led['faith']['hi']})`\n",
             f"### {led['headline']}", f"*{led['deck']}*\n", led["body"], "\n",
             "\n---\n## Fact-ledger\n```\n" + ledger_to_text(L) + "\n```\n"]
    fn.write_text("\n".join(lines), encoding="utf-8")


async def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    async with get_db() as db:
        if len(sys.argv) > 1:
            rows = [{"story_id": a, "band": "?", "article_count": None} for a in sys.argv[1:]]
        else:
            res = await db.execute(text(SAMPLE_SQL))
            rows = [dict(r._mapping) for r in res.fetchall()]
        print(f"A/B on {len(rows)} stories  (model={GEN_MODEL}, vote={VOTE})\n", flush=True)
        summary = []
        for idx, row in enumerate(rows, 1):
            sid, band = row["story_id"], row.get("band", "?")
            L = await load_ledger(db, sid)
            srcs = await load_sources(db, sid)
            title = L["cluster"].get("representative_title", "")[:70]
            print(f"[{idx}/{len(rows)}] {band:<6} {sid[:8]}  arts={row.get('article_count')} "
                  f"sources={len(srcs)}  {title}", flush=True)
            try:
                led = await run_ledger(L)
                src = await run_source(L, srcs)
            except Exception as exc:
                print(f"   !! errored: {str(exc)[:160]}", flush=True)
                continue
            write_story(idx, sid, band, L, srcs, led, src)
            row_m = {"band": band, "sid": sid[:8], "arts": row.get("article_count"),
                     "src_fed": len(srcs), "led_w": led["words"], "src_w": src["words"],
                     "led_faith": led["faith"]["hard_faith"], "src_faith": src["faith"]["hard_faith"],
                     "src_contra": src["faith"]["contra"], "overlap": src["overlap"]}
            summary.append(row_m)
            print(f"   ledger={led['words']}w (faith {led['faith']['hard_faith']}%)  →  "
                  f"source={src['words']}w (faith {src['faith']['hard_faith']}%, "
                  f"contra {src['faith']['contra']}, overlap {src['overlap']})", flush=True)
        (OUT_DIR / "_metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print("\n===== A/B SUMMARY (words: ledger → source · hard-faith%) =====", flush=True)
        for m in summary:
            print(f"{m['band']:<6} {m['sid']} arts={str(m['arts']):<4} "
                  f"{m['led_w']:>4}w→{m['src_w']:>4}w  "
                  f"faith {m['led_faith']}%→{m['src_faith']}%  "
                  f"contra={m['src_contra']} overlap={m['overlap']}", flush=True)
        if summary:
            import statistics as st
            print(f"\nMEDIAN words: ledger {st.median(m['led_w'] for m in summary):.0f} → "
                  f"source {st.median(m['src_w'] for m in summary):.0f}", flush=True)
            print(f"MEAN hard-faith: ledger {st.mean(m['led_faith'] for m in summary):.0f}% → "
                  f"source {st.mean(m['src_faith'] for m in summary):.0f}%  "
                  f"(source contradictions total: {sum(m['src_contra'] for m in summary)})", flush=True)
        print(f"\nWrote {len(summary)} comparisons + _metrics.json to {OUT_DIR}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
