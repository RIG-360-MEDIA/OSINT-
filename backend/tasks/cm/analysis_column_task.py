"""
Daily editorial Analysis column for the CM Page v2.

Cadence: 06:00, 12:00, 18:00 IST. Each run:
  1. Pulls the top 30 cm-relevant articles + the previous published
     column for continuity.
  2. Asks Groq for a 5-paragraph editorial: lede / sequence / stakes /
     foresight / recommendation. Plus eyebrow, byline, headline, deck,
     pull_quote, endnote, and an explicit cite_ids list.
  3. Validates each cite_id against the articles table. If at least
     MIN_VALID_CITES resolve, the draft is published immediately
     (status='published', published_at=now()). Otherwise the row is
     persisted with status='rejected' and the previous published
     draft stays visible.

The /api/cm/analysis read endpoint returns the most recent
status='published' row.
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


CONTEXT_ARTICLE_LIMIT = 12

# Politically-relevant keyword bag for the editorial signals query. An
# article must hit at least one of these in title or body to be eligible
# (otherwise sports / lifestyle / film coverage drowns the column).
POLITICAL_KEYWORDS = (
    'cm', 'chief minister', 'revanth', 'kcr', 'ktr', 'harish rao',
    'bandi sanjay', 'kavitha', 'opposition', 'minister', 'governor',
    'cabinet', 'budget', 'protest', 'rally', 'caste', 'reservation',
    'farmer', 'congress', 'brs', 'bjp', 'aimim', 'assembly',
    'high court', 'hydra', 'musi', 'group-1', 'irrigation'
)
MIN_VALID_CITES = 4

ANALYSIS_PROMPT = (
    "You are the senior editor of a daily intelligence brief written for the Chief "
    "Minister of {state}. Synthesize the recent signals below into a 5-paragraph "
    "editorial column.\n\n"
    "Required structure:\n"
    "  Paragraph 1 (Lede): the single most-important thing that changed in the last "
    "24 hours.\n"
    "  Paragraph 2 (Sequence): how the day unfolded — who said what, when.\n"
    "  Paragraph 3 (Stakes): what this means strategically for the chair.\n"
    "  Paragraph 4 (Foresight): what the next 24-72h likely look like.\n"
    "  Paragraph 5 (Recommendation): one operative line — the lever the chair has.\n\n"
    "Hard rules:\n"
    "  - Each assertion of fact must be grounded in the signal list below. Do not "
    "invent quotes, names, or numbers.\n"
    "  - Tone is third-person editorial, sentence avg 18-22 words, no jargon.\n"
    "  - Reference at least 4 of the article ids in the cite_ids array.\n\n"
    "Return JSON with this exact shape:\n"
    "{{\n"
    '  "eyebrow": "Analysis · 14:37 IST",\n'
    '  "byline": "By the Strategy Desk",\n'
    '  "headline": "...",\n'
    '  "deck": "...",\n'
    '  "paragraphs": ["...", "...", "...", "...", "..."],\n'
    '  "pull_quote": "...",\n'
    '  "endnote": "Filed HH:MM IST · circulation: principal secretariat",\n'
    '  "cite_ids": ["<uuid>", "<uuid>", ...]\n'
    "}}\n\n"
    "Recent signals:\n"
    "{signals}\n\n"
    "Previous column (for continuity, do not repeat verbatim):\n"
    "{previous}\n"
)


async def _gather_signals(state: str | None) -> list[dict[str, Any]]:
    sql = """
        SELECT a.id, a.title, COALESCE(a.lead_text_translated, a.lead_text_original, '') AS body,
               a.published_at,
               s.name AS source_name
        FROM articles a
        JOIN article_districts ad ON ad.article_id = a.id
        JOIN districts d ON d.id = ad.district_id
        LEFT JOIN sources s ON s.id = a.source_id
        WHERE a.collected_at > NOW() - INTERVAL '24 hours'
          AND a.nlp_processed = TRUE
          AND a.is_duplicate = FALSE
          AND d.state_code = COALESCE(:state, d.state_code)
          AND (a.title ILIKE ANY(:kw_patterns)
            OR COALESCE(a.lead_text_translated, a.lead_text_original, '') ILIKE ANY(:kw_patterns))
        GROUP BY a.id, s.name
        ORDER BY a.published_at DESC NULLS LAST
        LIMIT :lim
    """
    async with get_db() as db:
        kw_patterns = [f"%{k}%" for k in POLITICAL_KEYWORDS]
        rows = (await db.execute(
            text(sql),
            {"state": state, "lim": CONTEXT_ARTICLE_LIMIT, "kw_patterns": kw_patterns},
        )).all()
    return [
        {
            "id": str(r.id),
            "title": r.title or "",
            "body": (r.body or "")[:400],
            "source": r.source_name or "Unknown",
        }
        for r in rows
    ]


async def _previous_column(state: str | None) -> str | None:
    sql = """
        SELECT headline, paragraphs FROM cm_analysis_drafts
        WHERE state_code = COALESCE(:state, state_code) AND status = 'published'
        ORDER BY published_at DESC LIMIT 1
    """
    async with get_db() as db:
        row = (await db.execute(text(sql), {"state": state})).first()
    if not row:
        return None
    paragraphs = row.paragraphs or []
    return f"Headline: {row.headline}\n" + "\n\n".join(paragraphs)


def _format_signals(signals: list[dict[str, Any]]) -> str:
    lines = []
    for s in signals:
        lines.append(f"- id={s['id']} · {s['source']}: {s['title']} — {s['body']}")
    return "\n".join(lines)


async def _llm_draft(state: str | None, signals: list[dict[str, Any]]) -> dict[str, Any] | None:
    try:
        from backend.nlp.groq_client import call_groq, ANALYSIS_MODEL
    except ImportError:
        try:
            from backend.nlp.groq_client import call_groq, FAST_MODEL as ANALYSIS_MODEL  # type: ignore
        except ImportError:
            logger.warning("groq_client unavailable; skipping analysis draft")
            return None
    previous = await _previous_column(state) or "(none — fresh start)"
    prompt = ANALYSIS_PROMPT.format(
        state="Telangana" if state == "TG" else (state or "the state"),
        signals=_format_signals(signals),
        previous=previous,
    )
    try:
        resp = await call_groq(
            system="Return raw JSON only. No prose, no Markdown.",
            user=prompt,
            model=ANALYSIS_MODEL,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("groq analysis call failed: %s", exc)
        return None
    if not resp:
        return None
    raw = resp.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE | re.MULTILINE).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("groq analysis returned non-JSON: %s", raw[:200])
        return None


async def _persist(state: str | None, draft: dict[str, Any], status: str, valid_count: int) -> None:
    cite_ids: list[UUID] = []
    for raw in draft.get("cite_ids") or []:
        if isinstance(raw, UUID):
            cite_ids.append(raw)
        elif isinstance(raw, str):
            try:
                cite_ids.append(UUID(raw.strip()))
            except ValueError:
                continue
    sql = """
        INSERT INTO cm_analysis_drafts
            (state_code, status, eyebrow, byline, headline, deck, paragraphs,
             pull_quote, endnote, cite_ids, valid_cite_count, generated_at,
             published_at, rejected_at, model)
        VALUES
            (:state, :status, :eyebrow, :byline, :headline, :deck,
             CAST(:paragraphs AS jsonb), :pull, :endnote,
             CAST(:cites AS uuid[]), :valid_count, now(),
             :published_at, :rejected_at, :model)
    """
    paragraphs = draft.get("paragraphs") or []
    if not isinstance(paragraphs, list):
        paragraphs = [str(paragraphs)]
    paragraphs = [str(p)[:2000] for p in paragraphs[:6]]
    async with get_db() as db:
        await db.execute(
            text(sql),
            {
                "state": state or "TG",
                "status": status,
                "eyebrow": (draft.get("eyebrow") or "")[:160],
                "byline": (draft.get("byline") or "By the Strategy Desk")[:160],
                "headline": (draft.get("headline") or "")[:400],
                "deck": (draft.get("deck") or "")[:600],
                "paragraphs": json.dumps(paragraphs),
                "pull": (draft.get("pull_quote") or "")[:600],
                "endnote": (draft.get("endnote") or "")[:300],
                "cites": [str(u) for u in cite_ids],
                "valid_count": valid_count,
                "published_at": "now()" if status == "published" else None,
                "rejected_at": "now()" if status == "rejected" else None,
                "model": "groq:analysis",
            },
        )
        await db.commit()


async def _run(state: str | None) -> dict[str, Any]:
    signals = await _gather_signals(state)
    if len(signals) < MIN_VALID_CITES:
        logger.info("analysis_column: insufficient signals (%d) for state=%s", len(signals), state)
        return {"status": "skipped", "signals": len(signals)}

    draft = await _llm_draft(state, signals)
    if draft is None:
        return {"status": "no_draft"}

    raw_cites = draft.get("cite_ids") or []
    async with get_db() as db:
        validation = await validate_cite_ids(db, raw_cites)

    if len(validation.valid_ids) >= MIN_VALID_CITES:
        await _persist(state, draft, status="published", valid_count=len(validation.valid_ids))
        return {"status": "published", "valid_cites": len(validation.valid_ids), "invalid_cites": len(validation.invalid_ids)}
    else:
        await _persist(state, draft, status="rejected", valid_count=len(validation.valid_ids))
        logger.info(
            "analysis_column: rejected — only %d/%d cites valid (need >=%d)",
            len(validation.valid_ids), len(raw_cites), MIN_VALID_CITES,
        )
        return {"status": "rejected", "valid_cites": len(validation.valid_ids)}


@app.task(name="tasks.cm.analysis_column", bind=True, max_retries=1)
def analysis_column(self, state: str = "TG") -> dict[str, Any]:  # type: ignore[no-untyped-def]
    try:
        return asyncio.run(_run(state))
    except Exception as exc:
        logger.exception("analysis_column failed")
        raise self.retry(exc=exc, countdown=600)
