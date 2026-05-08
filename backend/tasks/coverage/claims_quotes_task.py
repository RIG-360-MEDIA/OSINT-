"""
tasks.extract_claims_quotes_for_article

Per-article extraction of factual claims + attributed quotes using
Groq with strict JSON schema. Fired by process_nlp_batch right after
LaBSE embedding lands, OR manually for backfill.

Idempotent: skipped if articles.claims_extracted = TRUE for that article.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db
from backend.nlp.groq_client import (
    FAST_MODEL,
    GroqCallFailed,
    GroqQuotaExhausted,
    call_groq,
)

logger = logging.getLogger(__name__)


_EXTRACTION_SYSTEM = (
    "You extract factual claims and attributed quotes from a news article. "
    "Return STRICT JSON: { "
    "claims: [{text: 'short factual claim', subject: 'entity name', "
    "predicate: 'verb-phrase', object: 'short object'}, ...] (max 6), "
    "quotes: [{speaker: 'name as written', text: 'exact quote', "
    "is_direct: true|false}, ...] (max 6) }. "
    "Skip opinion / editorial commentary — only verifiable factual claims. "
    "No prose outside JSON. No fences."
)


async def _fetch_article(article_id: str) -> dict[str, Any] | None:
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT id::text, title,
                       COALESCE(full_text_scraped,
                                lead_text_translated,
                                lead_text_original) AS body,
                       claims_extracted, quotes_extracted
                FROM articles
                WHERE id = :aid
                """
            ),
            {"aid": article_id},
        )
        row = result.fetchone()
    if not row:
        return None
    return {
        "id": row.id,
        "title": row.title,
        "body": (row.body or "")[:3500],
        "claims_extracted": row.claims_extracted,
        "quotes_extracted": row.quotes_extracted,
    }


async def _resolve_entity_id(name: str) -> str | None:
    async with get_db() as db:
        result = await db.execute(
            text(
                "SELECT id::text FROM entity_dictionary "
                "WHERE LOWER(canonical_name) = LOWER(:n) LIMIT 1"
            ),
            {"n": name},
        )
        row = result.fetchone()
    return row[0] if row else None


async def _persist(article_id: str, parsed: dict[str, Any]) -> dict[str, int]:
    claims = parsed.get("claims") or []
    quotes = parsed.get("quotes") or []

    n_claims = 0
    n_quotes = 0

    async with get_db() as db:
        for c in claims[:6]:
            text_value = str(c.get("text", ""))[:1000]
            if not text_value.strip():
                continue
            subject = c.get("subject") or ""
            entity_id = await _resolve_entity_id(subject) if subject else None
            await db.execute(
                text(
                    """
                    INSERT INTO article_claims
                      (article_id, claim_text, subject_entity_id, subject_text,
                       predicate, object_text, confidence)
                    VALUES (:a, :t, :e, :s, :p, :o, :c)
                    """
                ),
                {
                    "a": article_id,
                    "t": text_value,
                    "e": entity_id,
                    "s": subject[:240] or None,
                    "p": (c.get("predicate") or "")[:120] or None,
                    "o": (c.get("object") or "")[:240] or None,
                    "c": 0.7,
                },
            )
            n_claims += 1

        for q in quotes[:6]:
            quote_text_value = str(q.get("text", ""))[:1500]
            speaker = str(q.get("speaker", ""))[:240]
            if not quote_text_value.strip() or not speaker.strip():
                continue
            speaker_entity = await _resolve_entity_id(speaker)
            await db.execute(
                text(
                    """
                    INSERT INTO article_quotes
                      (article_id, speaker_name, speaker_entity_id,
                       quote_text, is_direct)
                    VALUES (:a, :sp, :se, :qt, :d)
                    """
                ),
                {
                    "a": article_id,
                    "sp": speaker,
                    "se": speaker_entity,
                    "qt": quote_text_value,
                    "d": bool(q.get("is_direct", True)),
                },
            )
            n_quotes += 1

        # Mark article as extracted (idempotency guard).
        await db.execute(
            text(
                "UPDATE articles SET claims_extracted = TRUE, "
                "quotes_extracted = TRUE WHERE id = :a"
            ),
            {"a": article_id},
        )
        await db.commit()

    return {"claims": n_claims, "quotes": n_quotes}


async def _run(article_id: str, force: bool = False) -> dict[str, Any]:
    article = await _fetch_article(article_id)
    if not article:
        return {"error": "article not found"}
    if not force and article["claims_extracted"] and article["quotes_extracted"]:
        return {"skipped": "already extracted"}

    body = article["body"]
    if len(body) < 80:
        # not enough text to extract anything meaningful
        async with get_db() as db:
            await db.execute(
                text(
                    "UPDATE articles SET claims_extracted = TRUE, "
                    "quotes_extracted = TRUE WHERE id = :a"
                ),
                {"a": article_id},
            )
            await db.commit()
        return {"skipped": "body too short"}

    user_prompt = f"Title: {article['title']}\n\nBody:\n{body}"
    try:
        raw = await call_groq(
            system=_EXTRACTION_SYSTEM,
            user=user_prompt,
            task_type="rag_response",
            model=FAST_MODEL,
            json_response=True,
        )
        parsed = json.loads(raw)
    except (GroqQuotaExhausted, GroqCallFailed) as exc:
        logger.warning("claim extraction Groq failed for %s: %s", article_id, exc)
        return {"error": str(exc)}
    except json.JSONDecodeError:
        logger.warning("claim extraction JSON parse failed for %s", article_id)
        return {"error": "json parse"}

    return await _persist(article_id, parsed)


@app.task(
    name="tasks.extract_claims_quotes_for_article",
    bind=True,
    max_retries=2,
)
def extract_claims_quotes_for_article(  # type: ignore[no-untyped-def]
    self,
    article_id: str,
    force: bool = False,
) -> dict:
    """Idempotent per-article extraction. Routed to nlp queue."""
    return asyncio.run(_run(article_id, force=force))
