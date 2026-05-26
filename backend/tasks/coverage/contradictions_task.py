"""
tasks.refresh_contradictions

Daily at 04:30 UTC. For each entity with >= 3 articles in the last 48h,
finds candidate claim pairs (one claim per article, top by confidence)
and asks Groq with strict JSON schema "do these claims contradict?"

Persists confirmed contradictions to article_contradictions.

NLI is done via Groq (no torch / DeBERTa add). Conservative: only flag
when model says contradiction probability > 0.6 AND confidence > 0.5.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db
from backend.nlp.groq_client import (
    QUALITY_MODEL,
    GroqCallFailed,
    GroqQuotaExhausted,
    call_groq,
)

logger = logging.getLogger(__name__)


_WINDOW_HOURS = 48
_MIN_ARTICLES_PER_ENTITY = 3
_MAX_PAIRS_PER_ENTITY = 5  # cost cap


_NLI_SYSTEM = (
    "You are a fact-alignment analyst. Given two short factual claims about "
    "the same subject, return STRICT JSON: "
    "{ contradicts: true|false, confidence: 0.0-1.0, "
    "  divergence_summary: 'one short paragraph (max 60 words) explaining "
    "  WHY they conflict, in plain prose; empty string if not contradicting' }. "
    "Treat semantic equivalents (paraphrases) as agreement, not "
    "contradiction. Distinguish opinion from factual conflict — only "
    "factual conflicts count. No prose outside JSON. No fences."
)


async def _entities_with_recent_volume() -> list[str]:
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT LOWER(TRIM(ac.subject_text)) AS entity_id,
                       COUNT(*) AS volume
                FROM article_claims ac
                JOIN articles a ON a.id = ac.article_id
                WHERE ac.subject_text IS NOT NULL
                  AND LENGTH(TRIM(ac.subject_text)) BETWEEN 4 AND 80
                  AND LOWER(TRIM(ac.subject_text)) NOT IN
                      ('article','story','report','piece','news','we','they','officials','the article','this article')
                  AND a.collected_at > NOW() - make_interval(hours => :hrs)
                GROUP BY LOWER(TRIM(ac.subject_text))
                HAVING COUNT(DISTINCT a.source_id) >= :min_count
                ORDER BY COUNT(*) DESC
                LIMIT 50
                """
            ),
            {"hrs": _WINDOW_HOURS, "min_count": _MIN_ARTICLES_PER_ENTITY},
        )
        rows = result.fetchall()
    return [r.entity_id for r in rows]


async def _candidate_claim_pairs(entity_id: str) -> list[tuple[dict, dict]]:
    """Top claims per article for this entity, paired across distinct articles."""
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT DISTINCT ON (ac.article_id)
                       ac.id::text AS claim_id, ac.article_id::text,
                       ac.claim_text, ac.confidence,
                       a.source_id::text AS source_id
                FROM article_claims ac
                JOIN articles a ON a.id = ac.article_id
                WHERE LOWER(TRIM(ac.subject_text)) = :eid
                  AND a.collected_at > NOW() - make_interval(hours => :hrs)
                ORDER BY ac.article_id, ac.confidence DESC
                LIMIT 12
                """
            ),
            {"eid": entity_id, "hrs": _WINDOW_HOURS},
        )
        claims = [
            {
                "claim_id": r.claim_id,
                "article_id": r.article_id,
                "claim_text": r.claim_text,
                "confidence": r.confidence,
                "source_id": r.source_id,
            }
            for r in result.fetchall()
        ]

    pairs: list[tuple[dict, dict]] = []
    # Lexicographic order by (claim_id_a, claim_id_b) where a < b — matches
    # the CHECK constraint on article_contradictions.
    for i, ci in enumerate(claims):
        for cj in claims[i + 1 :]:
            if ci["source_id"] == cj["source_id"]:
                continue  # same source, doesn't count as cross-source dispute
            a, b = sorted([ci, cj], key=lambda c: c["claim_id"])
            pairs.append((a, b))
            if len(pairs) >= _MAX_PAIRS_PER_ENTITY:
                return pairs
    return pairs


async def _check_pair(a: dict, b: dict) -> dict | None:
    user_prompt = (
        f"Claim A: {a['claim_text']}\n"
        f"Claim B: {b['claim_text']}\n\n"
        "Do these contradict on a factual level?"
    )
    try:
        raw = await call_groq(
            system=_NLI_SYSTEM,
            user=user_prompt,
            task_type="classification",
            model=QUALITY_MODEL,
            json_response=True,
        )
        parsed = json.loads(raw)
    except (GroqQuotaExhausted, GroqCallFailed, json.JSONDecodeError) as exc:
        logger.warning("contradictions NLI failed: %s", exc)
        return None

    if not parsed.get("contradicts"):
        return None
    confidence = float(parsed.get("confidence", 0.0))
    if confidence < 0.6:
        return None

    return {
        "summary": str(parsed.get("divergence_summary", ""))[:600],
        "confidence": confidence,
    }


async def _persist_contradiction(
    a: dict, b: dict, entity_id: str, finding: dict[str, Any]
) -> None:
    async with get_db() as db:
        await db.execute(
            text(
                """
                INSERT INTO article_contradictions
                  (claim_a_id, claim_b_id, entity_id,
                   divergence_summary, confidence)
                VALUES (:a, :b, :e, :s, :c)
                ON CONFLICT (claim_a_id, claim_b_id) DO UPDATE SET
                  divergence_summary = EXCLUDED.divergence_summary,
                  confidence = EXCLUDED.confidence,
                  detected_at = NOW(),
                  is_resolved = FALSE
                """
            ),
            {
                "a": a["claim_id"],
                "b": b["claim_id"],
                "e": None,  # entity_id FK NULL — we now key by subject_text
                "s": finding["summary"],
                "c": finding["confidence"],
            },
        )
        await db.commit()


async def _run() -> dict[str, Any]:
    entity_ids = await _entities_with_recent_volume()
    flagged = 0
    pairs_checked = 0

    for eid in entity_ids:
        pairs = await _candidate_claim_pairs(eid)
        for a, b in pairs:
            pairs_checked += 1
            finding = await _check_pair(a, b)
            if finding:
                try:
                    await _persist_contradiction(a, b, eid, finding)
                    flagged += 1
                except Exception as exc:  # noqa: BLE001
                    logger.exception("contradiction persist failed: %s", exc)

    return {
        "entities_scanned": len(entity_ids),
        "pairs_checked": pairs_checked,
        "flagged": flagged,
    }


def _flag(name: str) -> bool:
    raw = os.getenv(name, "").strip().lower()
    return raw in ("1", "true", "yes", "on")


@app.task(
    name="tasks.refresh_contradictions",
    bind=True,
    max_retries=0,
)
def refresh_contradictions(self) -> dict:  # type: ignore[no-untyped-def]
    if not _flag("FEATURE_CONTRADICTIONS"):
        return {"skipped": "feature flag off"}
    return asyncio.run(_run())
