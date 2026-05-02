"""
Rotating Lead headlines for the CM Page v2 hero.

Every 5 minutes:
  1. Pick the top 5 CM-relevant articles in the last 24h, ranked by a
     composite of cm_relevance × recency × district_confidence.
  2. For each, ask Groq for a 2-3-line eyebrow + headline that
     paraphrases the article and includes the article's UUID in
     ``cite_ids``.
  3. Validate each cite_id against the articles table. If validation
     passes (>=1 valid cite per row), write rank=0..4 with
     validated=TRUE, rejected=FALSE. If a cite fails, fall back to a
     verbatim article-title row with cite_ids = [article.id] and
     model = 'fallback'.

The read endpoint /api/cm/lead returns the most-recent batch where
validated=TRUE AND rejected=FALSE.

Routing: nlp queue (Groq calls — IO-bound, OK to share with NLP).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any
from uuid import UUID

from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db
from backend.nlp.cm.cite_validate import validate_cite_ids

logger = logging.getLogger(__name__)


CANDIDATES_PER_BATCH = 5
HEADLINE_PROMPT = (
    "You are a senior intelligence editor writing a one-line news ticker for the "
    "Chief Minister of {state}. Given the article below, return a JSON object with "
    "exactly two fields:\n"
    '  - "eyebrow": SHORT-CAPS kicker (max 6 words, e.g. "WHAT CHANGED · 14:37").\n'
    '  - "headline": a single sentence, 18-32 words, paraphrased from the article. '
    "Do not invent facts beyond the article.\n\n"
    "Article id: {article_id}\n"
    "Article title: {title}\n"
    "Article body: {body}\n\n"
    "Respond with raw JSON only — no Markdown, no preface."
)


async def _candidate_articles(state: str | None) -> list[dict[str, Any]]:
    """Top 5 articles in the last 24h, primary-district-tagged for the state."""
    sql = """
        SELECT a.id, a.title, COALESCE(a.lead_text_translated, a.lead_text_original, '') AS body,
               a.published_at, a.collected_at,
               ad.confidence AS district_confidence
        FROM articles a
        JOIN article_districts ad ON ad.article_id = a.id AND ad.is_primary = TRUE
        JOIN districts d ON d.id = ad.district_id
        WHERE a.collected_at > NOW() - INTERVAL '24 hours'
          AND a.nlp_processed = TRUE
          AND a.is_duplicate = FALSE
          AND d.state_code = COALESCE(:state, d.state_code)
        ORDER BY (
            ad.confidence
            * EXP(-EXTRACT(EPOCH FROM (NOW() - a.collected_at)) / 21600.0)  -- 6h half-life
        ) DESC
        LIMIT :n
    """
    async with get_db() as db:
        rows = (await db.execute(text(sql), {"state": state, "n": CANDIDATES_PER_BATCH})).all()
    return [
        {
            "id": str(r.id),
            "title": r.title or "",
            "body": (r.body or "")[:1200],
            "district_confidence": float(r.district_confidence or 0.0),
        }
        for r in rows
    ]


async def _llm_headline(state: str | None, article: dict[str, Any]) -> dict[str, Any] | None:
    """Call Groq for a single article. Returns {eyebrow, headline} or None on failure."""
    try:
        from backend.nlp.groq_client import call_groq, FAST_MODEL
    except ImportError:
        logger.warning("groq_client unavailable; skipping LLM headline")
        return None
    prompt = HEADLINE_PROMPT.format(
        state="Telangana" if state == "TG" else (state or "the state"),
        article_id=article["id"],
        title=article["title"],
        body=article["body"][:600],
    )
    try:
        resp = await call_groq(system="Return raw JSON only.", user=prompt, model=FAST_MODEL)
    except Exception as exc:  # noqa: BLE001
        logger.warning("groq headline call failed: %s", exc)
        return None
    if not resp:
        return None
    raw = resp.strip()
    # Tolerate fenced JSON.
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE | re.MULTILINE).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("groq returned non-JSON: %s", raw[:120])
        return None
    eyebrow = parsed.get("eyebrow")
    headline = parsed.get("headline")
    if not (isinstance(eyebrow, str) and isinstance(headline, str) and headline.strip()):
        return None
    return {"eyebrow": eyebrow.strip()[:120], "headline": headline.strip()[:400]}


async def _persist_batch(state: str | None, batch: list[dict[str, Any]]) -> None:
    insert_sql = """
        INSERT INTO cm_lead_headlines
            (state_code, rank, eyebrow, headline, cite_ids,
             generated_at, model, validated, rejected, rejection_reason)
        VALUES
            (:state, :rank, :eyebrow, :headline, CAST(:cites AS uuid[]),
             now(), :model, :validated, :rejected, :reason)
    """
    async with get_db() as db:
        for row in batch:
            await db.execute(
                text(insert_sql),
                {
                    "state": state or "TG",
                    "rank": row["rank"],
                    "eyebrow": row["eyebrow"],
                    "headline": row["headline"],
                    "cites": row["cite_ids"],
                    "model": row["model"],
                    "validated": row["validated"],
                    "rejected": row["rejected"],
                    "reason": row.get("rejection_reason"),
                },
            )
        await db.commit()


async def _run(state: str | None) -> dict[str, int]:
    candidates = await _candidate_articles(state)
    if not candidates:
        logger.info("lead_headline: no candidates for state=%s", state)
        return {"generated": 0, "fallback": 0}

    rows: list[dict[str, Any]] = []
    n_generated = 0
    n_fallback = 0
    for rank, art in enumerate(candidates):
        article_id = art["id"]
        try:
            article_uuid = UUID(article_id)
        except ValueError:
            continue

        async with get_db() as db:
            validation = await validate_cite_ids(db, [article_uuid])

        if not validation.all_valid:
            # Article disappeared between candidate fetch and validation. Skip.
            continue

        llm = await _llm_headline(state, art)
        if llm is None:
            # Fallback: literal title + cite to the article itself.
            rows.append({
                "rank": rank,
                "eyebrow": "TODAY · LIVE FEED",
                "headline": art["title"][:400],
                "cite_ids": [article_uuid],
                "model": "fallback",
                "validated": True,
                "rejected": False,
                "rejection_reason": None,
            })
            n_fallback += 1
        else:
            rows.append({
                "rank": rank,
                "eyebrow": llm["eyebrow"],
                "headline": llm["headline"],
                "cite_ids": [article_uuid],
                "model": "groq:fast",
                "validated": True,
                "rejected": False,
                "rejection_reason": None,
            })
            n_generated += 1

    if rows:
        await _persist_batch(state, rows)
    return {"generated": n_generated, "fallback": n_fallback}


@app.task(name="tasks.cm.lead_headline", bind=True, max_retries=1)
def lead_headline(self, state: str = "TG") -> dict[str, int]:  # type: ignore[no-untyped-def]
    """Run the lead-headline generation for one state. Default TG."""
    try:
        return asyncio.run(_run(state))
    except Exception as exc:
        logger.exception("lead_headline failed")
        raise self.retry(exc=exc, countdown=120)
