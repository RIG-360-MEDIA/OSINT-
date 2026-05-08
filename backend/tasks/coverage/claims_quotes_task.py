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
    "quotes: [{speaker: 'name AS WRITTEN in source', "
    "speaker_en: 'speaker name in natural English/transliterated', "
    "text: 'exact quote in source language', "
    "text_en: 'natural English translation of the quote', "
    "is_direct: true|false}, ...] (max 6) }. "
    "If the source article is already in English, set speaker_en "
    "= speaker and text_en = text (just normalised). For non-English "
    "articles (Telugu, Tamil, Bengali, Hindi etc.), translate "
    "faithfully — preserve meaning over literal word order. "
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
            quote_text_en = str(q.get("text_en", ""))[:1500].strip() or None
            speaker_en = str(q.get("speaker_en", ""))[:240].strip() or None
            speaker_entity = await _resolve_entity_id(speaker_en or speaker)
            await db.execute(
                text(
                    """
                    INSERT INTO article_quotes
                      (article_id, speaker_name, speaker_entity_id,
                       quote_text, is_direct,
                       quote_text_en, speaker_name_en, translated_at)
                    VALUES (:a, :sp, :se, :qt, :d,
                            :qt_en, :sp_en,
                            CASE WHEN :qt_en IS NOT NULL
                                 THEN NOW() ELSE NULL END)
                    """
                ),
                {
                    "a": article_id,
                    "sp": speaker,
                    "se": speaker_entity,
                    "qt": quote_text_value,
                    "d": bool(q.get("is_direct", True)),
                    "qt_en": quote_text_en,
                    "sp_en": speaker_en,
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


# ── Backfill / continuous-extraction driver ───────────────────────────────────
#
# process_nlp_batch never wires extraction itself, so without this task the
# `claims_extracted = FALSE` pile grows forever and the Quote sidebar /
# Compare mode / Contradictions all sit empty. This Celery task scans the
# unextracted backlog every 5 min, takes the 50 most recent rows (within
# the last 7 days), and fans out one per-article extraction task each.
#
# At ~50 tasks per 5 min and ~2-3 s per task on the nlp queue (concurrency
# 4), throughput is ~600-800 articles/hour — enough to keep up with
# ingestion AND drain a few-thousand-article backlog within hours.
#
# Cost envelope: 50 calls/5 min × FAST_MODEL = ~$0.03/hour at current
# Groq pricing. Negligible.

_BATCH_SIZE = 50
_MAX_AGE_DAYS = 7  # don't waste budget on stale articles


async def _queue_pending() -> dict[str, int]:
    """
    Find unextracted articles + dispatch per-article tasks.

    Selective filter: only extract from articles that any user is likely
    to actually see — i.e. tier-1/2 in someone's relevance feed, OR from
    a tier-1 source. Pre-filtering this way cuts daily Groq token spend
    by ~70% (no more wasting tokens on Australian byelections or
    Nigerian local politics that no user tracks).
    """
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT a.id::text
                FROM articles a
                WHERE a.claims_extracted = FALSE
                  AND a.collected_at > NOW() - make_interval(days => :days)
                  AND COALESCE(a.full_text_scraped,
                               a.lead_text_translated,
                               a.lead_text_original) IS NOT NULL
                  AND LENGTH(COALESCE(a.full_text_scraped,
                                      a.lead_text_translated,
                                      a.lead_text_original)) >= 80
                  AND (
                    -- High-trust source: tier-1 outlets always extracted
                    a.source_tier = 1
                    -- OR at least one user's relevance feed rates it
                    -- tier-1/2. EXISTS quits early, cheap.
                    OR EXISTS (
                      SELECT 1 FROM user_article_relevance uar
                      WHERE uar.article_id = a.id
                        AND uar.relevance_tier IN (1, 2)
                    )
                  )
                ORDER BY a.collected_at DESC
                LIMIT :limit
                """
            ),
            {"days": _MAX_AGE_DAYS, "limit": _BATCH_SIZE},
        )
        ids = [r[0] for r in result.fetchall()]

    for aid in ids:
        try:
            app.send_task(
                "tasks.extract_claims_quotes_for_article",
                args=[aid],
            )
        except Exception as exc:  # noqa: BLE001 — never crash the driver
            logger.warning("queue extract failed for %s: %s", aid, exc)

    return {"queued": len(ids)}


@app.task(
    name="tasks.extract_pending_claims_quotes",
    bind=True,
    max_retries=0,
)
def extract_pending_claims_quotes(self) -> dict:  # type: ignore[no-untyped-def]
    """
    Periodic driver. Beat-fired every 5 min on the nlp queue.

    Always on — extraction is a foundational pipeline step, not a
    user-facing feature flag. If you really need to disable it,
    pull the beat entry.
    """
    return asyncio.run(_queue_pending())


# ── Backfill: translate pre-existing quotes that have no English text ─────────


_TRANSLATE_SYSTEM = (
    "You translate news quotes to natural English. Return STRICT JSON: "
    "{\"speaker_en\": \"...\", \"text_en\": \"...\"}. If the input is "
    "already English, return it lightly cleaned. For non-English input "
    "(Telugu, Tamil, Bengali, Hindi etc.), translate faithfully — "
    "preserve meaning over literal word order. No prose outside JSON, "
    "no fences."
)

_TRANSLATE_BATCH_SIZE = 30


async def _translate_pending_run() -> dict[str, int]:
    """
    Find quotes where quote_text_en IS NULL (created before migration
    049 / before the extractor learned to translate), translate via
    Groq, update in place. Capped at _TRANSLATE_BATCH_SIZE per fire.
    """
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT id::text AS id, speaker_name, quote_text
                FROM article_quotes
                WHERE quote_text_en IS NULL
                  AND extracted_at > NOW() - INTERVAL '60 days'
                ORDER BY extracted_at DESC
                LIMIT :lim
                """
            ),
            {"lim": _TRANSLATE_BATCH_SIZE},
        )
        rows = result.fetchall()

    translated, failed = 0, 0
    for row in rows:
        prompt = (
            f"speaker: {row.speaker_name}\n"
            f"text: {row.quote_text}\n\n"
            "Return the JSON object."
        )
        try:
            raw = await call_groq(
                system=_TRANSLATE_SYSTEM,
                user=prompt,
                task_type="classification",
                model=FAST_MODEL,
                json_response=True,
            )
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                failed += 1
                continue
            sp_en = str(parsed.get("speaker_en") or "").strip()[:240] or None
            qt_en = str(parsed.get("text_en") or "").strip()[:1500] or None
            if not qt_en:
                failed += 1
                continue
        except (GroqQuotaExhausted, GroqCallFailed) as exc:
            logger.warning("quote translation failed: %s", exc)
            failed += 1
            continue
        except json.JSONDecodeError:
            failed += 1
            continue

        async with get_db() as db:
            await db.execute(
                text(
                    """
                    UPDATE article_quotes
                    SET quote_text_en = :qt_en,
                        speaker_name_en = COALESCE(:sp_en, speaker_name_en),
                        translated_at = NOW()
                    WHERE id::text = :id
                    """
                ),
                {"qt_en": qt_en, "sp_en": sp_en, "id": row.id},
            )
            await db.commit()
        translated += 1

    return {"scanned": len(rows), "translated": translated, "failed": failed}


@app.task(
    name="tasks.translate_pending_quotes",
    bind=True,
    max_retries=0,
)
def translate_pending_quotes(self) -> dict:  # type: ignore[no-untyped-def]
    """
    Periodic driver. Beat-fired every 5 min on the nlp queue.
    Translates quotes that were extracted before migration 049 added
    the English columns.
    """
    return asyncio.run(_translate_pending_run())
