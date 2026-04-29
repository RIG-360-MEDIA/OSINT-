"""
Daily promise-status scoring against retrieved evidence.

For each row in cm_promises, run a small RAG query around the pledge text
and ask Groq to return one of {kept, in_progress, stalled, broken,
unknown} along with a confidence. Below the floor, status reverts to
'unknown' rather than guessing.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db
from backend.nlp.groq_client import (
    GroqCallFailed,
    GroqQuotaExhausted,
    extract_json,
)
from backend.nlp.rag_engine import retrieve_relevant_articles

logger = logging.getLogger(__name__)

# Lowered from 0.55 → 0.35 so the LLM can surface "best-effort" pledge
# statuses against the current global-news corpus. Once the TG-political
# ingestion is producing meaningful coverage of these pledges, raise this
# back to 0.55 to require strong grounding.
CONFIDENCE_FLOOR = 0.35

_SYSTEM = (
    "You assess whether a public political promise has been kept, is in\n"
    "progress, has stalled, or has been broken — based ONLY on the\n"
    "supplied evidence. Return STRICT JSON:\n"
    "{\n"
    "  \"status\": \"kept\"|\"in_progress\"|\"stalled\"|\"broken\"|\"unknown\",\n"
    "  \"confidence\": <float in [0,1]>,\n"
    "  \"evidence_url\": <url string from the evidence list, or empty>\n"
    "}\n"
    "If the evidence is insufficient, return status='unknown' with low confidence."
)


async def _evidence_chunks(pledge: str) -> tuple[list[str], list[str]]:
    try:
        async with get_db() as db:
            outcome = await retrieve_relevant_articles(
                query=pledge,
                user_id="db4b9207-51aa-4d39-a7bf-e6fab34c3465",
                db=db,
                top_k=5,
            )
    except Exception as exc:  # noqa: BLE001
        logger.info("promise rag retrieve failed: %s", exc)
        return ([], [])
    rows = outcome[0] if isinstance(outcome, tuple) else (outcome or [])
    items: list[str] = []
    urls: list[str] = []
    for row in rows:
        # RAG engine returns dicts with text_snippet (not lead_text_*).
        if isinstance(row, dict):
            title = row.get("title") or ""
            body = (
                row.get("text_snippet")
                or row.get("lead_text_translated")
                or row.get("lead_text_original")
                or ""
            )
            url = row.get("url") or ""
        else:
            title = getattr(row, "title", None) or ""
            body = (
                getattr(row, "text_snippet", None)
                or getattr(row, "lead_text_translated", None)
                or ""
            )
            url = getattr(row, "url", None) or ""
        if title or body:
            items.append(f"- {title.strip()}: {body.strip()[:600]}")
            urls.append(url)
    return (items, urls)


async def _score(pledge: str, owner_party: str) -> dict[str, Any] | None:
    items, urls = await _evidence_chunks(pledge)
    if not items:
        return None
    user_prompt = (
        f"Pledge owner party: {owner_party}\n"
        f"Pledge text: {pledge}\n\n"
        f"Evidence (each line is a recent news item):\n" + "\n".join(items)
    )
    try:
        raw = await extract_json(system=_SYSTEM, user=user_prompt)
    except (GroqQuotaExhausted, GroqCallFailed) as exc:
        logger.info("promise score failed: %s", exc)
        return None
    payload = raw if isinstance(raw, dict) else None
    if isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    status = (payload.get("status") or "unknown").strip().lower()
    if status not in {"kept", "in_progress", "stalled", "broken", "unknown"}:
        status = "unknown"
    try:
        conf = float(payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    if conf < CONFIDENCE_FLOOR:
        status = "unknown"
    evidence_url = (payload.get("evidence_url") or "").strip()
    if evidence_url and evidence_url not in urls:
        evidence_url = ""
    return {"status": status, "confidence": conf, "evidence_url": evidence_url or None}


async def _run() -> int:
    sql = """
        SELECT id, pledge_text, owner_party, status
        FROM cm_promises
        WHERE last_scored_at IS NULL
           OR last_scored_at < now() - interval '24 hours'
        ORDER BY last_scored_at NULLS FIRST
        LIMIT 30
    """
    update = """
        UPDATE cm_promises
           SET status = :status,
               status_confidence = :conf,
               last_evidence_url = :url,
               last_status_change = CASE WHEN status <> :status THEN now() ELSE last_status_change END,
               last_scored_at = now()
         WHERE id = :id
    """
    n = 0
    async with get_db() as db:
        rows = (await db.execute(text(sql))).all()
        for r in rows:
            try:
                result = await _score(r.pledge_text, r.owner_party)
            except Exception as exc:  # noqa: BLE001
                logger.warning("promise score failed for %s: %s", r.id, exc)
                continue
            if not result:
                await db.execute(text(update), {
                    "id": r.id, "status": "unknown", "conf": 0.0, "url": None,
                })
            else:
                await db.execute(text(update), {
                    "id": r.id,
                    "status": result["status"],
                    "conf": result["confidence"],
                    "url": result["evidence_url"],
                })
            n += 1
        await db.commit()
    return n


@app.task(name="tasks.cm.score_promise_status", bind=True, max_retries=1)
def score_promise_status(self) -> dict[str, int]:
    try:
        return {"scored": asyncio.run(_run())}
    except Exception as exc:
        logger.exception("score_promise_status failed")
        raise self.retry(exc=exc, countdown=900)
