"""
Daily counter-narrative drafts for the top hostile issues.

Cite-ID guardrail in nlp/cm/counter_narrative.py rejects any output where
a cite ID is not in the retrieved grounding set; rejected rows are stored
with rejected=TRUE and never surfaced via /api/cm/counter-narratives.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db
from backend.nlp.cm.counter_narrative import generate_for_issue
from backend.nlp.rag_engine import retrieve_relevant_articles

logger = logging.getLogger(__name__)

TOP_N_ISSUES = 5
GROUNDING_K = 8


async def _hostile_issues() -> list[dict[str, Any]]:
    sql = """
        WITH triad AS (
            SELECT cie.issue_id,
                   AVG(CASE s.stance
                       WHEN 'opposition_attack' THEN -1.0
                       WHEN 'ruling_supportive' THEN  1.0
                       ELSE 0.0
                   END * COALESCE(s.confidence, 0.0))::float AS avg_stance,
                   COUNT(*) AS n
            FROM cm_issue_evidence cie
            LEFT JOIN cm_stance_scores s
              ON s.source_id = cie.source_id AND s.source_kind = cie.source_kind
            WHERE cie.attached_at > now() - interval '36 hours'
            GROUP BY cie.issue_id
        )
        SELECT i.id, i.label, i.state, t.avg_stance, t.n
        FROM cm_issues i
        JOIN triad t ON t.issue_id = i.id
        WHERE t.n >= 4
        ORDER BY t.avg_stance ASC, t.n DESC
        LIMIT :lim
    """
    async with get_db() as db:
        rows = (await db.execute(text(sql), {"lim": TOP_N_ISSUES})).all()
    return [
        {"id": r.id, "label": r.label, "state": r.state, "avg_stance": float(r.avg_stance or 0)}
        for r in rows
    ]


async def _opposition_quotes(issue_id: int) -> list[str]:
    sql = """
        SELECT quote
        FROM cm_spokesperson_quotes
        WHERE issue_id = :iid
          AND stance = 'opposition_attack'
          AND extracted_at > now() - interval '7 days'
        ORDER BY extracted_at DESC
        LIMIT 2
    """
    async with get_db() as db:
        rows = (await db.execute(text(sql), {"iid": issue_id})).all()
    return [r.quote for r in rows]


async def _grounding_chunks(issue_label: str, user_id: str) -> list[dict[str, Any]]:
    """Use the existing RAG engine to retrieve relevant articles for the
    issue label. Signature mirrors `retrieve_relevant_articles(query,
    user_id, db, top_k=...)` from backend/nlp/rag_engine.py which returns
    a `(rows, _, _)` tuple."""
    try:
        async with get_db() as db:
            outcome = await retrieve_relevant_articles(
                query=issue_label,
                user_id=user_id or "db4b9207-51aa-4d39-a7bf-e6fab34c3465",
                db=db,
                top_k=GROUNDING_K,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("RAG retrieve failed for %s: %s", issue_label, exc)
        return []
    rows = outcome[0] if isinstance(outcome, tuple) else (outcome or [])
    chunks: list[dict[str, Any]] = []
    for row in rows:
        # The RAG engine returns dicts shaped:
        # {article_id, title, url, source_name, ..., text_snippet, distance}.
        if isinstance(row, dict):
            chunk_id = row.get("article_id") or row.get("id")
            title = row.get("title") or ""
            body = (
                row.get("text_snippet")
                or row.get("lead_text_translated")
                or row.get("lead_text_original")
                or ""
            )
        else:
            chunk_id = getattr(row, "article_id", None) or getattr(row, "id", None)
            title = getattr(row, "title", None) or ""
            body = (
                getattr(row, "text_snippet", None)
                or getattr(row, "lead_text_translated", None)
                or getattr(row, "lead_text_original", None)
                or ""
            )
        if not chunk_id:
            continue
        # IDs may be UUIDs — stringify so the cite-ID guardrail compares safely.
        chunks.append({"id": str(chunk_id), "kind": "article", "text": f"{title}. {body}"})
    return chunks


async def _persist(issue_id: int, state: str | None, cn) -> None:
    insert = """
        INSERT INTO cm_counter_narratives (
            issue_id, state, generated_at, talking_points, grounding_doc_ids,
            grounding_kinds, model, retry_count, rejected
        ) VALUES (
            :iid, :state, now(), CAST(:tp AS jsonb), :gids, :gkinds,
            :model, :retries, :rej
        )
    """
    async with get_db() as db:
        await db.execute(
            text(insert),
            {
                "iid": issue_id,
                "state": state,
                "tp": json.dumps(
                    [{"text": p.text, "cites": p.cites} for p in cn.talking_points]
                ),
                "gids": cn.grounding_doc_ids,
                "gkinds": cn.grounding_kinds,
                "model": cn.model,
                "retries": cn.retry_count,
                "rej": cn.rejected,
            },
        )
        await db.commit()


async def _run() -> dict[str, int]:
    issues = await _hostile_issues()
    n_generated = 0
    n_rejected = 0
    for it in issues:
        opp_quotes = await _opposition_quotes(it["id"])
        chunks = await _grounding_chunks(it["label"], user_id="db4b9207-51aa-4d39-a7bf-e6fab34c3465")
        if not chunks:
            continue
        try:
            cn = await generate_for_issue(
                issue_label=it["label"],
                opposition_quotes=opp_quotes,
                chunks=chunks,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("counter-narrative gen failed for %s: %s", it["id"], exc)
            continue
        await _persist(it["id"], it["state"], cn)
        if cn.rejected:
            n_rejected += 1
        else:
            n_generated += 1
    return {"generated": n_generated, "rejected": n_rejected}


@app.task(name="tasks.cm.generate_counter_narratives", bind=True, max_retries=1)
def generate_counter_narratives(self) -> dict[str, int]:
    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("generate_counter_narratives failed")
        raise self.retry(exc=exc, countdown=900)
