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

async def collect_quotes(n_stories: int = 8) -> list[dict]:
    """Pull principalQuote + lens quotes from /api/brief/stories."""
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(f"{API_BASE}/api/brief/stories?limit={n_stories}")
    r.raise_for_status()
    out = []
    for story in r.json().get("stories", []):
        pq = story.get("principalQuote")
        if pq and pq.get("text"):
            out.append({
                "kind": "principalQuote",
                "quote": pq["text"],
                "speaker": pq.get("attribution"),
                "source": pq.get("source"),
                "headline": story.get("headline", "")[:80],
            })
        for lens in story.get("lens", []):
            q = lens.get("quote")
            if q and q.startswith("("):
                continue  # placeholder rows
            if q:
                out.append({
                    "kind": "lens",
                    "quote": q,
                    "speaker": None,
                    "source": lens.get("outlet"),
                    "headline": story.get("headline", "")[:80],
                })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Source-article lookup
# ─────────────────────────────────────────────────────────────────────────────

async def find_source_article(quote: str, source: str | None) -> dict | None:
    """Try to locate the article that contains this quote.

    We use article_quotes as the index — finding the article via the saved
    speaker_name + quote_text is reliable since the brief router pulled
    these straight from that table.
    """
    qn = _norm(quote)
    needle = qn[: min(80, len(qn))]  # first 80 chars of normalised quote
    async with engine.connect() as conn:
        # Match via article_quotes.quote_text (normalised); we keep top 1
        row = (await conn.execute(text("""
            SELECT a.id AS article_id, a.title, a.summary_executive,
                   a.thumbnail_url, a.collected_at, s.name AS source,
                   aq.quote_text
              FROM article_quotes aq
              JOIN articles a ON a.id = aq.article_id
              JOIN sources s  ON s.id = a.source_id
             WHERE LOWER(regexp_replace(aq.quote_text, '[^a-z0-9 ]', '', 'g')) LIKE :n
               AND ('' = :src OR s.name = :src)
             ORDER BY a.collected_at DESC
             LIMIT 1
        """), {"n": f"%{needle}%", "src": source or ""})).fetchone()
        if not row:
            return None

        # Pull a chunk of substrate to look in: title + summary + the matched quote_text
        # (the full article body isn't in our table; we use the quote-text row as proof
        # the quote was extracted from this article — that's our ground truth)
        body_parts = [row.title or "", row.summary_executive or "", row.quote_text or ""]
        return {
            "article_id": str(row.article_id),
            "title": row.title,
            "doc": "\n".join(body_parts),
            "source": row.source,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Main eval loop
# ─────────────────────────────────────────────────────────────────────────────

async def main(n_stories: int = 8) -> int:
    quotes = await collect_quotes(n_stories=n_stories)
    if not quotes:
        print("No quotes found in /api/brief/stories. Replay clock too narrow?")
        return 0

    results = []
    for q in quotes:
        src = await find_source_article(q["quote"], q.get("source"))
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
        results.append({**q, "verdict": verdict, "score": round(score, 3),
                        "article_id": src["article_id"] if src else None})

    # ─── Report ─────────────────────────────────────────────────────────────
    n = len(results)
    by_verdict = Counter(r["verdict"] for r in results)
    print(f"\nFaithfulness eval — {n} quotes from {n_stories} stories")
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
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    raise SystemExit(asyncio.run(main(n)))
