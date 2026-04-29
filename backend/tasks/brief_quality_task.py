"""
Brief quality scorecard cron.

Runs once a day (Beat schedule ``score-brief-quality-daily``, 01:00 UTC,
queue ``brief``). For every brief produced in the last 48 hours, computes
the rubric defined in ``docs/qa/brief-remediation-plan.md`` Phase 2 #10
and inserts/updates a row in ``brief_quality_scores``.

The rubric is intentionally cheap and deterministic — no LLM call is
made here. The job is to detect regressions (stale articles, citation
density drops, ``[Generation failed`` markers reappearing) so an
operator can react before users notice. A human or a downstream
dashboard reads ``brief_quality_scores`` for the time-series view.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db
from backend.nlp.brief_validator import count_words, validate_citations

logger = logging.getLogger(__name__)


_BRACKET_CITE_RE = re.compile(r"\[\d{1,3}\]")
_PILLAR_CITE_RE = re.compile(r"Paper:|Doc:|Social:|Video:")
_SECTION_HEADERS = (
    "SITUATION STATUS",
    "KEY DEVELOPMENTS",
    "ENTITIES TODAY",
    "SIGNALS TO WATCH",
    "FINANCIAL PULSE",
    "SOURCE COVERAGE",
)


def _split_sections(content: str) -> dict[str, str]:
    """Cheap markdown splitter: ``## SECTION`` headings → body text.

    Mirrors :mod:`frontend/src/app/brief/lib/parseBrief` so we score the
    same shape the user sees. Anything before the first known header
    (the title block) is dropped.
    """
    sections: dict[str, str] = {}
    if not content:
        return sections

    pattern = re.compile(
        r"^##\s+(" + "|".join(re.escape(s) for s in _SECTION_HEADERS) + r")\s*$",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(content))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        sections[m.group(1)] = content[start:end].strip()
    return sections


def _overall(
    *,
    section_count: int,
    bracket_cites: int,
    failure_marker_count: int,
    invalid_index_count: int,
    avg_recency_days: float | None,
) -> float:
    """Weighted 0.0–1.0 summary of the rubric."""
    score = 1.0
    # Section completeness — 6 sections expected, lose 0.1 per missing.
    score -= (6 - section_count) * 0.1
    # Failure markers shouldn't appear at all.
    if failure_marker_count > 0:
        score -= 0.3
    # Hallucinated cites are a quality red flag.
    if invalid_index_count > 0:
        score -= 0.15
    # Citation density — fewer than 5 bracket cites means thin sourcing.
    if bracket_cites < 5:
        score -= 0.1
    # Recency drift — cap at 0.2 lost for a 7+ day average.
    if avg_recency_days is not None:
        score -= min(0.2, max(0.0, (avg_recency_days - 1.5) * 0.04))
    return max(0.0, round(score, 3))


async def _score_one_brief(db, row) -> dict[str, Any]:
    """Score one ``briefs`` row and return the columns to upsert."""
    m = row._mapping
    content: str = m["content"] or ""
    sections = _split_sections(content)

    bracket_cites = len(_BRACKET_CITE_RE.findall(content))
    pillar_cites = len(_PILLAR_CITE_RE.findall(content))
    failure_marker_count = content.count("[Generation failed")

    source_counts: dict[str, int] = m["source_counts"] or {}
    article_count = int(source_counts.get("articles") or m["articles_used"] or 0)
    govt = int(source_counts.get("govt_docs") or 0)
    paper = int(source_counts.get("newspaper_clippings") or 0)
    social = int(source_counts.get("social_posts") or 0)
    video = int(source_counts.get("video_clips") or 0)

    invalid_per_section: list[dict[str, Any]] = []
    section_word_counts: dict[str, int] = {}
    for name, body in sections.items():
        section_word_counts[name] = count_words(body)
        v = validate_citations(
            name, body,
            article_count=article_count,
            govt_doc_count=govt,
            newspaper_count=paper,
            social_count=social,
            video_count=video,
        )
        if v.invalid_article_indexes:
            invalid_per_section.append({
                "section": name,
                "invalid": list(v.invalid_article_indexes),
            })

    # Recency — re-run the same query the runner uses, but for this
    # brief's user, scoped to 'last 7 days' so we always get a number.
    recency_row = (
        await db.execute(
            text(
                """
                WITH p AS (
                    SELECT a.published_at,
                           CURRENT_DATE - a.published_at::date AS days_old
                    FROM user_article_relevance uar
                    JOIN articles a ON a.id = uar.article_id
                    WHERE uar.user_id = :uid
                      AND uar.relevance_tier IN (1, 2)
                      AND a.nlp_confidence != 'error'
                      AND COALESCE(a.is_duplicate, FALSE) = FALSE
                      AND a.published_at >= NOW() - INTERVAL '7 days'
                    ORDER BY uar.relevance_tier ASC, uar.score_final DESC
                    LIMIT 30
                )
                SELECT AVG(days_old) AS avg_d, MAX(days_old) AS max_d,
                       COUNT(*) FILTER (
                           WHERE published_at >= NOW() - INTERVAL '36 hours'
                       ) AS within_36h
                FROM p
                """
            ),
            {"uid": str(m["user_id"])},
        )
    ).fetchone()

    avg_d = float(recency_row._mapping["avg_d"] or 0) if recency_row else None
    max_d = float(recency_row._mapping["max_d"] or 0) if recency_row else None
    within_36h = int(recency_row._mapping["within_36h"] or 0) if recency_row else 0

    invalid_index_count = sum(len(x["invalid"]) for x in invalid_per_section)

    return {
        "user_id": str(m["user_id"]),
        "brief_date": m["brief_date"],
        "has_situation_status": "SITUATION STATUS" in sections,
        "has_key_developments": "KEY DEVELOPMENTS" in sections,
        "has_entities_today": "ENTITIES TODAY" in sections,
        "has_signals_to_watch": "SIGNALS TO WATCH" in sections,
        "has_financial_pulse": "FINANCIAL PULSE" in sections,
        "has_source_coverage": "SOURCE COVERAGE" in sections,
        "bracket_cites": bracket_cites,
        "pillar_cites": pillar_cites,
        "failure_marker_count": failure_marker_count,
        "invalid_indexes": json.dumps(invalid_per_section),
        "article_recency_avg_days": avg_d,
        "article_recency_max_days": max_d,
        "articles_within_36h": within_36h,
        "section_word_counts": json.dumps(section_word_counts),
        "overall_score": _overall(
            section_count=len(sections),
            bracket_cites=bracket_cites,
            failure_marker_count=failure_marker_count,
            invalid_index_count=invalid_index_count,
            avg_recency_days=avg_d,
        ),
    }


_UPSERT_SQL = text(
    """
    INSERT INTO brief_quality_scores (
        user_id, brief_date,
        has_situation_status, has_key_developments, has_entities_today,
        has_signals_to_watch, has_financial_pulse, has_source_coverage,
        bracket_cites, pillar_cites, failure_marker_count, invalid_indexes,
        article_recency_avg_days, article_recency_max_days, articles_within_36h,
        section_word_counts, overall_score, scored_at
    ) VALUES (
        :user_id, :brief_date,
        :has_situation_status, :has_key_developments, :has_entities_today,
        :has_signals_to_watch, :has_financial_pulse, :has_source_coverage,
        :bracket_cites, :pillar_cites, :failure_marker_count,
        CAST(:invalid_indexes AS jsonb),
        :article_recency_avg_days, :article_recency_max_days, :articles_within_36h,
        CAST(:section_word_counts AS jsonb), :overall_score, NOW()
    )
    ON CONFLICT (user_id, brief_date) DO UPDATE SET
        has_situation_status     = EXCLUDED.has_situation_status,
        has_key_developments     = EXCLUDED.has_key_developments,
        has_entities_today       = EXCLUDED.has_entities_today,
        has_signals_to_watch     = EXCLUDED.has_signals_to_watch,
        has_financial_pulse      = EXCLUDED.has_financial_pulse,
        has_source_coverage      = EXCLUDED.has_source_coverage,
        bracket_cites            = EXCLUDED.bracket_cites,
        pillar_cites             = EXCLUDED.pillar_cites,
        failure_marker_count     = EXCLUDED.failure_marker_count,
        invalid_indexes          = EXCLUDED.invalid_indexes,
        article_recency_avg_days = EXCLUDED.article_recency_avg_days,
        article_recency_max_days = EXCLUDED.article_recency_max_days,
        articles_within_36h      = EXCLUDED.articles_within_36h,
        section_word_counts      = EXCLUDED.section_word_counts,
        overall_score            = EXCLUDED.overall_score,
        scored_at                = NOW()
    """
)


async def _score_recent_briefs() -> dict[str, int]:
    """Re-score every brief from the last 48 hours."""
    async with get_db() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT user_id, brief_date, content, articles_used,
                           source_counts
                    FROM briefs
                    WHERE generated_at >= NOW() - INTERVAL '48 hours'
                    ORDER BY generated_at DESC
                    """
                )
            )
        ).fetchall()

        scored = 0
        for row in rows:
            try:
                payload = await _score_one_brief(db, row)
                await db.execute(_UPSERT_SQL, payload)
                scored += 1
            except Exception as exc:  # noqa: BLE001 — never let one bad row block the cohort
                logger.exception(
                    "score_brief_quality: row %s failed: %s",
                    row._mapping.get("user_id"), exc,
                )

        await db.commit()
        return {"considered": len(rows), "scored": scored}


@app.task(name="tasks.score_brief_quality", bind=True, max_retries=0)
def score_brief_quality(self) -> dict:  # type: ignore[no-untyped-def]
    """Daily Beat task. Populates ``brief_quality_scores``."""
    out = asyncio.run(_score_recent_briefs())
    logger.info("score_brief_quality complete: %s", out)
    return out


__all__ = ["score_brief_quality"]
