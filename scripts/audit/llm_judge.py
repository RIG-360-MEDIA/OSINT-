"""llm_judge.py — Layer 5 of the deep data quality audit.

Stratified sample of articles → LLM-as-judge → per-field scores.

For each article, send the LLM:
  - The article's title + summary_executive + lead_text_translated (or scraped)
  - The structured extraction (primary_subject, article_type, actors[], etc.)
  - Ask: "Does each extracted field match the article? Score 0-10. Flag wrong ones."

Outputs JSONL with one row per judged article. A separate freeze step
selects the highest-confidence rows as the regression gold set.

Uses backend.nlp.groq_client unified pool (52 slots = 1 Ollama + 24 Groq + 27 Cerebras).

Usage:
    python3 scripts/audit/llm_judge.py --sample 200          # smoke
    python3 scripts/audit/llm_judge.py --sample 5000 --resume # production
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("llm_judge")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
QUALITY_DIR = REPO_ROOT / "docs" / "quality"
SAMPLES_DIR = QUALITY_DIR / "samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
csv.field_size_limit(10 * 1024 * 1024)  # 10MB per field

sys.path.insert(0, "/app")
try:
    from backend.database import get_db  # noqa: E402
    HAVE_BACKEND = True
except ImportError:
    HAVE_BACKEND = False
    log.warning("backend.database not importable — must run inside rig-backend")


JUDGE_SYSTEM = (
    "You are auditing news-article extractions for accuracy. Given an article's "
    "text and a structured extraction made by another LLM, your job is to rate "
    "how well each extracted field matches the article. Be strict. Output STRICT JSON."
)

JUDGE_USER_TEMPLATE = """ARTICLE
Source: {source}  |  Language: {lang}  |  Published: {published_at}
Title: {title}
Body excerpt:
{body}

EXTRACTION (made by an earlier LLM pass)
{extraction_json}

For each field below, score how well the extracted value matches the article (0=wrong/hallucinated, 10=exact match). Also give an overall accuracy 0-10.

Output STRICT JSON only (no preamble):
{{
  "primary_subject_score": <0-10>,
  "summary_executive_score": <0-10>,
  "article_type_score": <0-10>,
  "actors_score": <0-10>,
  "event_dates_score": <0-10>,
  "overall_score": <0-10>,
  "issues": ["<short issue 1>", "<short issue 2>", ...],
  "confidence": <0.0-1.0>
}}"""


async def _query_db(sql: str, params: dict | None = None) -> list[dict[str, Any]]:
    """Run a SELECT against rig-postgres via the existing async DB session."""
    from sqlalchemy import text
    async with get_db() as db:
        result = await db.execute(text(sql), params or {})
        return [dict(r._mapping) for r in result.fetchall()]


async def stratified_sample(n: int) -> list[dict[str, str]]:
    """Sample n articles stratified across source × extraction_version × month.

    Uses NTILE buckets + md5 ordering for deterministic, reproducible sampling.
    """
    query = """
        SELECT a.id::text AS article_id, s.name AS source,
               a.language_detected AS lang,
               a.published_at::text AS published_at,
               a.collected_at::text AS collected_at,
               a.extraction_version::text AS ev, a.article_type,
               LEFT(a.title, 200) AS title,
               LEFT(a.primary_subject, 300) AS primary_subject,
               LEFT(a.summary_executive, 800) AS summary_executive,
               LEFT(a.lead_text_translated, 2500) AS lead_text_translated
          FROM (
            SELECT a.*, ROW_NUMBER() OVER (
              PARTITION BY a.source_id,
                           DATE_TRUNC('month', a.published_at),
                           a.extraction_version
              ORDER BY md5(a.id::text || 'judge_v1')
            ) AS rn
            FROM articles a
            WHERE a.substrate_status = 'ok'
              AND a.extraction_version >= 2
              AND a.summary_executive IS NOT NULL
              AND LENGTH(a.summary_executive) > 80
          ) a
          JOIN sources s ON s.id = a.source_id
          WHERE rn <= 50
          ORDER BY md5(a.id::text || 'judge_global')
          LIMIT :n
    """
    log.info("Sampling %d articles (stratified)...", n)
    rows = await _query_db(query, {"n": int(n)})
    log.info("Got %d sampled articles", len(rows))
    return rows


async def judge_article(client: "Any", article: dict[str, str]) -> dict[str, Any]:
    """Call the LLM judge on one article. Returns the parsed verdict + metadata."""
    body = (article.get("lead_text_translated") or article.get("summary_executive") or "")[:2000]
    extraction = {
        "primary_subject": article.get("primary_subject"),
        "summary_executive": article.get("summary_executive"),
        "article_type": article.get("article_type"),
    }

    user = JUDGE_USER_TEMPLATE.format(
        source=article.get("source", "?"),
        lang=article.get("lang", "?"),
        published_at=article.get("published_at", "?"),
        title=article.get("title", "")[:200],
        body=body,
        extraction_json=json.dumps(extraction, ensure_ascii=False, indent=2),
    )

    try:
        from backend.nlp.groq_client import call_groq
    except ImportError:
        # If we're running outside the container, mock the call.
        log.warning("backend.nlp.groq_client not importable — using stub")
        return {"article_id": article.get("article_id"),
                "error": "groq_client_not_available"}

    try:
        raw = await call_groq(
            system=JUDGE_SYSTEM, user=user,
            task_type="classification", json_response=True,
            max_tokens_override=400,
        )
        parsed = json.loads(raw)
        return {"article_id": article.get("article_id"),
                "source": article.get("source"),
                "lang": article.get("lang"),
                "verdict": parsed}
    except Exception as exc:
        return {"article_id": article.get("article_id"),
                "source": article.get("source"),
                "error": str(exc)[:200]}


async def judge_all(articles: list[dict[str, str]], concurrency: int = 8) -> list[dict[str, Any]]:
    sem = asyncio.Semaphore(concurrency)
    results: list[dict[str, Any]] = []

    async def _one(a):
        async with sem:
            r = await judge_article(None, a)
            return r

    tasks = [_one(a) for a in articles]
    done = 0
    t0 = time.time()
    for coro in asyncio.as_completed(tasks):
        r = await coro
        results.append(r)
        done += 1
        if done % 25 == 0 or done == len(articles):
            rate = done / max(time.time() - t0, 1)
            log.info("Judged %d/%d (%.1f/sec)", done, len(articles), rate)
    return results


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-field median scores + flag findings."""
    successes = [r for r in results if "verdict" in r and "error" not in r]
    errors = [r for r in results if "error" in r]
    if not successes:
        return {"sampled": len(results), "successes": 0, "errors": len(errors)}

    def median(vals):
        s = sorted(vals)
        n = len(s)
        if not n:
            return None
        return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2

    field_scores = {
        "primary_subject_score": [],
        "summary_executive_score": [],
        "article_type_score": [],
        "actors_score": [],
        "event_dates_score": [],
        "overall_score": [],
    }
    for r in successes:
        v = r["verdict"]
        for k in field_scores:
            x = v.get(k)
            if isinstance(x, (int, float)):
                field_scores[k].append(float(x))

    summary: dict[str, Any] = {
        "sampled": len(results), "successes": len(successes),
        "errors": len(errors), "median_scores": {},
        "p25_scores": {},
    }
    for k, vals in field_scores.items():
        if vals:
            summary["median_scores"][k] = round(median(vals), 2)
            vals_sorted = sorted(vals)
            summary["p25_scores"][k] = round(vals_sorted[len(vals_sorted) // 4], 2)

    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sample", type=int, default=200)
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--out", help="JSONL output path (default: docs/quality/samples/...)")
    args = p.parse_args(argv)

    run_date = datetime.now().strftime("%Y-%m-%d")
    out_path = Path(args.out) if args.out else (
        SAMPLES_DIR / f"judge_results_{run_date}_{args.sample}.jsonl"
    )

    async def _run():
        articles = await stratified_sample(args.sample)
        if not articles:
            log.error("No articles sampled.")
            return None
        log.info("Running judge with concurrency=%d ...", args.concurrency)
        return await judge_all(articles, args.concurrency)

    results = asyncio.run(_run())
    if results is None:
        return 1

    with open(out_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    log.info("Wrote %d rows to %s", len(results), out_path)

    summary = summarize(results)
    summary_path = QUALITY_DIR / f"judge_summary_{run_date}.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log.info("Summary: %s", json.dumps(summary, indent=2)[:600])
    log.info("Wrote summary to %s", summary_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
