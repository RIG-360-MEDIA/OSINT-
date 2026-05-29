"""Faithfulness evaluator for brief principalQuotes + lens-card quotes.

For each picked quote, fetch the source article's full text and check whether
the quote appears (verbatim OR with 90%+ trigram-token overlap). Flags any
quote that isn't grounded in its source.

The "LLM hallucinated a quote" failure mode is the most dangerous one we have
in news AI — confident wrongness attributed to a politician. This is the
on-call check that catches it before a customer screenshots it.

Run:
    cd products/osint/backend
    .venv/Scripts/python ../../../scripts/eval/faithfulness.py
"""
from __future__ import annotations

import asyncio
import re
import sys
from collections import Counter
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Load backend .env to get DB URL + API base
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / "products" / "osint" / "backend" / ".env")

import os  # noqa: E402

API_BASE = os.environ.get("FAITHFULNESS_API_BASE", "https://robin-osi.rig360media.com/osint")

# Import DB after env is loaded
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

DB_URL = os.environ["OSINT_DB_URL"]
engine = create_async_engine(DB_URL)


# ─────────────────────────────────────────────────────────────────────────────
# Faithfulness check helpers
# ─────────────────────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    """Lowercase + collapse whitespace + strip punctuation that LLMs vary."""
    return re.sub(r"[\s ]+", " ", re.sub(r"[\"'‘’“”.,!?;:()]", "", s.lower())).strip()


def _trigrams(s: str) -> Counter:
    n = _norm(s)
    return Counter(n[i:i + 3] for i in range(len(n) - 2)) if len(n) >= 3 else Counter()


def overlap_score(quote: str, doc: str) -> float:
    """Trigram-token overlap as a fraction of the quote's trigrams."""
    qg = _trigrams(quote)
    if not qg:
        return 0.0
    dg = _trigrams(doc)
    total = sum(qg.values())
    matched = sum(min(c, dg.get(g, 0)) for g, c in qg.items())
    return matched / total


def verbatim_in(quote: str, doc: str) -> bool:
    return _norm(quote) in _norm(doc)


# ─────────────────────────────────────────────────────────────────────────────
# Sample collection from the live brief API
# ─────────────────────────────────────────────────────────────────────────────

async def collect_quotes(n: int = 30) -> list[dict]:
    """Sample N quotes from article_quotes — the table the brief draws from.

    This is what the brief WOULD show if every cluster had quotes — same
    quality dimension, larger N. /api/brief/stories' principalQuote alone
    gives a tiny sample at certain sim_now values.
    """
    async with engine.connect() as conn:
        rows = (await conn.execute(text("""
            SELECT aq.quote_text, aq.speaker_name,
                   aq.context, aq.is_direct,
                   s.name AS source, a.title AS headline, a.id AS article_id,
                   ed.canonical_name AS speaker_canonical,
                   ed.entity_type AS speaker_type
              FROM article_quotes aq
              JOIN articles a ON a.id = aq.article_id
              JOIN sources s ON s.id = a.source_id
              LEFT JOIN entity_dictionary ed ON ed.id = aq.speaker_entity_id
             WHERE LENGTH(aq.quote_text) BETWEEN 40 AND 280
               AND aq.is_direct = TRUE
             ORDER BY RANDOM() LIMIT :n
        """), {"n": n})).fetchall()
    return [{
        "kind": "article_quote",
        "quote": r.quote_text,
        "speaker": r.speaker_canonical or r.speaker_name,
        "speaker_type": r.speaker_type,
        "source": r.source,
        "headline": (r.headline or "")[:80],
        "article_id": str(r.article_id),
        "context": r.context,
    } for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Source-article lookup
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_article_proxy(article_id: str) -> dict | None:
    """Fetch the article's title + summary + raw_text (when present) for
    verbatim search. Our 'document' to check the quote against."""
    async with engine.connect() as conn:
        row = (await conn.execute(text("""
            SELECT a.id, a.title, a.summary_executive, a.summary_snippet,
                   a.summary_preview, a.lead_text_original, a.lead_text_translated,
                   a.full_text_scraped, a.full_text_translated
              FROM articles a
             WHERE a.id = CAST(:aid AS uuid)
        """), {"aid": article_id})).fetchone()
    if not row:
        return None
    body = "\n".join([
        row.title or "",
        row.summary_executive or "",
        row.summary_snippet or "",
        row.summary_preview or "",
        row.lead_text_original or "",
        row.lead_text_translated or "",
        (row.full_text_scraped or "")[:50000],
        (row.full_text_translated or "")[:50000],
    ])
    return {"id": str(row.id), "doc": body, "title": row.title}


# ─────────────────────────────────────────────────────────────────────────────
# Main eval loop
# ─────────────────────────────────────────────────────────────────────────────

async def main(n: int = 30) -> int:
    quotes = await collect_quotes(n=n)
    if not quotes:
        print("No quotes in article_quotes. Drain hasn't extracted any yet?")
        return 0

    results = []
    for q in quotes:
        src = await fetch_article_proxy(q["article_id"])
        verdict = "UNGROUNDED"
        score = 0.0
        if src:
            doc = src["doc"]
            if verbatim_in(q["quote"], doc):
                verdict = "VERBATIM"
                score = 1.0
            else:
                score = overlap_score(q["quote"], doc)
                if score >= 0.90:
                    verdict = "NEAR_MATCH"
                elif score >= 0.50:
                    verdict = "PARTIAL"
                else:
                    verdict = "MISMATCH"
        results.append({**q, "verdict": verdict, "score": round(score, 3)})

    # ─── Report ─────────────────────────────────────────────────────────────
    n = len(results)
    by_verdict = Counter(r["verdict"] for r in results)
    print(f"\nFaithfulness eval — {n} quotes sampled from article_quotes")
    print(f"  API: {API_BASE}")
    print("─" * 78)
    for verdict in ("VERBATIM", "NEAR_MATCH", "PARTIAL", "MISMATCH", "UNGROUNDED"):
        c = by_verdict.get(verdict, 0)
        pct = round(100 * c / n, 1) if n else 0
        print(f"  {verdict:12s} {c:>3} ({pct:>5}%)")
    print("─" * 78)
    pass_pct = 100 * (by_verdict.get("VERBATIM", 0) + by_verdict.get("NEAR_MATCH", 0)) / n
    print(f"  PASS rate (VERBATIM + NEAR_MATCH ≥ 0.90): {pass_pct:.1f}%")
    print()

    # ─── Sample failures ────────────────────────────────────────────────────
    fails = [r for r in results if r["verdict"] in ("MISMATCH", "UNGROUNDED", "PARTIAL")]
    if fails:
        print(f"FAILURES ({len(fails)}):")
        for f in fails[:5]:
            print(f"\n  [{f['verdict']} score={f['score']}] in story: {f['headline']}")
            print(f"    kind   : {f['kind']}")
            print(f"    speaker: {f['speaker']}")
            print(f"    source : {f['source']}")
            print(f"    quote  : {f['quote'][:120]}")

    await engine.dispose()
    return 1 if (by_verdict.get("UNGROUNDED", 0) + by_verdict.get("MISMATCH", 0)) >= n // 3 else 0


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    raise SystemExit(asyncio.run(main(n)))
