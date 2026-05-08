"""
tasks.refresh_user_cards

Daily at 01:30 UTC. Iterates each unique definition_hash that has at least
one user_cards row, pulls last 48h matching articles, and asks Groq for
a structured 4-section summary. Multiple users tracking the same
definition_hash share one summary row (dedupe).

Sections:
    state         — 1 line current snapshot
    whats_new     — bullet list of recent developments
    why_matters   — chain-of-thought paragraph that reasons about why
                    these developments matter given user_intent
    watch_for     — bullet list of indicators to watch
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
    FAST_MODEL,
    GroqCallFailed,
    GroqQuotaExhausted,
    call_groq,
)

logger = logging.getLogger(__name__)


_SAMPLE_SIZE = 30
_WINDOW_HOURS = 48


_SYSTEM_PROMPT = (
    "You are an intelligence analyst writing a tracker card for a single "
    "subject (an entity, topic, or theme the user is tracking). Return "
    "STRICT JSON with shape: { state: 'one short line', "
    "whats_new: ['short bullet', 'short bullet', ...] (3-5 items), "
    "why_matters: 'one paragraph (max 80 words) of chain-of-thought "
    "reasoning that ties the recent developments to the user-stated "
    "intent — explain HOW one fact leads to another and what it implies', "
    "watch_for: ['short bullet', ...] (1-3 items) }. No prose outside "
    "JSON. No fences. Plain text only."
)


async def _fetch_articles_for_definition(
    entity_refs: list[str],
    topic_filters: list[str],
    geo_filter: list[str],
) -> list[dict[str, Any]]:
    """Pull last 48h articles matching the definition."""
    clauses: list[str] = ["a.is_duplicate IS NOT TRUE"]
    clauses.append("a.collected_at > NOW() - make_interval(hours => :hrs)")
    params: dict[str, Any] = {"hrs": _WINDOW_HOURS, "limit": _SAMPLE_SIZE}

    if entity_refs:
        # Match if any of the entity IDs appear in entities_extracted JSONB.
        clauses.append(
            "EXISTS (SELECT 1 FROM jsonb_array_elements(a.entities_extracted) elt "
            "WHERE elt->>'entity_id' = ANY(:ents))"
        )
        params["ents"] = entity_refs

    if topic_filters:
        clauses.append("a.topic_category = ANY(:topics)")
        params["topics"] = topic_filters

    if geo_filter:
        clauses.append("(a.geo_primary = ANY(:geo) OR a.geo_secondary && :geo)")
        params["geo"] = geo_filter

    where_sql = " AND ".join(clauses)

    async with get_db() as db:
        result = await db.execute(
            text(
                f"""
                SELECT a.id::text AS article_id,
                       a.title,
                       COALESCE(a.lead_text_translated, a.lead_text_original) AS lead,
                       a.published_at,
                       s.name AS source_name
                FROM articles a
                JOIN sources s ON s.id = a.source_id
                WHERE {where_sql}
                ORDER BY a.published_at DESC NULLS LAST
                LIMIT :limit
                """
            ),
            params,
        )
        rows = result.fetchall()

    return [
        {
            "article_id": r.article_id,
            "title": r.title,
            "lead": (r.lead or "")[:300],
            "source_name": r.source_name,
            "published_at": r.published_at.isoformat() if r.published_at else None,
        }
        for r in rows
    ]


def _build_prompt(
    label: str,
    user_intent: str | None,
    articles: list[dict[str, Any]],
) -> str:
    bullet_block = "\n".join(
        f"[{i+1}] {a['title']} — {a['source_name']}"
        for i, a in enumerate(articles)
    ) if articles else "(no articles in the last 48 hours)"

    intent_block = (
        f"User's stated intent: {user_intent}\n\n"
        if user_intent else ""
    )
    return (
        f"Subject: {label}\n\n"
        f"{intent_block}"
        f"Recent items (numbered, used as citations):\n{bullet_block}\n\n"
        "Return the JSON described in the system prompt. The 'why_matters' "
        "paragraph should explicitly reason about how these developments "
        "matter given the subject and the user's stated intent."
    )


async def _generate_summary(
    label: str,
    user_intent: str | None,
    articles: list[dict[str, Any]],
) -> dict[str, Any] | None:
    user_prompt = _build_prompt(label, user_intent, articles)
    try:
        raw = await call_groq(
            system=_SYSTEM_PROMPT,
            user=user_prompt,
            task_type="rag_response",
            model=FAST_MODEL,
            json_response=True,
        )
    except GroqQuotaExhausted:
        logger.warning("user_cards quota exhausted")
        return None
    except GroqCallFailed as exc:
        logger.warning("user_cards Groq call failed: %s", exc)
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("user_cards JSON parse failed: %.200s", raw)
        return None

    return {
        "state": str(parsed.get("state", ""))[:240],
        "whats_new": [str(s)[:240] for s in parsed.get("whats_new", [])][:6],
        "why_matters": str(parsed.get("why_matters", ""))[:1200],
        "watch_for": [str(s)[:240] for s in parsed.get("watch_for", [])][:4],
    }


async def _upsert_summary(
    definition_hash: str,
    sections: dict[str, Any],
    citations: list[str],
    sample_size: int,
) -> None:
    async with get_db() as db:
        await db.execute(
            text(
                """
                INSERT INTO user_card_summaries (
                    definition_hash, sections, citations,
                    generated_at, generated_by_model, sample_size
                ) VALUES (
                    :h, CAST(:s AS JSONB), CAST(:c AS JSONB),
                    NOW(), :m, :n
                )
                ON CONFLICT (definition_hash) DO UPDATE SET
                    sections = EXCLUDED.sections,
                    citations = EXCLUDED.citations,
                    generated_at = EXCLUDED.generated_at,
                    generated_by_model = EXCLUDED.generated_by_model,
                    sample_size = EXCLUDED.sample_size
                """
            ),
            {
                "h": definition_hash,
                "s": json.dumps(sections),
                "c": json.dumps(citations),
                "m": FAST_MODEL,
                "n": sample_size,
            },
        )
        # Touch last_refreshed_at on every card sharing this definition.
        await db.execute(
            text(
                "UPDATE user_cards SET last_refreshed_at = NOW() "
                "WHERE definition_hash = :h"
            ),
            {"h": definition_hash},
        )
        await db.commit()


async def _refresh_for_hash(
    definition_hash: str,
    label: str,
    user_intent: str | None,
    entity_refs: list[str],
    topic_filters: list[str],
    geo_filter: list[str],
) -> str:
    articles = await _fetch_articles_for_definition(
        entity_refs, topic_filters, geo_filter
    )
    summary = await _generate_summary(label, user_intent, articles)
    if summary is None:
        return "skipped"
    await _upsert_summary(
        definition_hash,
        summary,
        [a["article_id"] for a in articles],
        len(articles),
    )
    return "ok"


async def _refresh_all(only_definition_hash: str | None = None) -> dict[str, str]:
    """Find unique definition_hashes and refresh each."""
    async with get_db() as db:
        if only_definition_hash:
            result = await db.execute(
                text(
                    """
                    SELECT DISTINCT definition_hash, label, user_intent,
                                    entity_refs, topic_filters, geo_filter
                    FROM user_cards
                    WHERE definition_hash = :h
                    LIMIT 1
                    """
                ),
                {"h": only_definition_hash},
            )
        else:
            result = await db.execute(
                text(
                    """
                    SELECT DISTINCT ON (definition_hash)
                        definition_hash, label, user_intent,
                        entity_refs, topic_filters, geo_filter
                    FROM user_cards
                    ORDER BY definition_hash, created_at ASC
                    """
                )
            )
        rows = result.fetchall()

    statuses: dict[str, str] = {}
    for row in rows:
        try:
            entity_refs = row.entity_refs or []
            if isinstance(entity_refs, str):
                entity_refs = json.loads(entity_refs)
            topic_filters = row.topic_filters or []
            if isinstance(topic_filters, str):
                topic_filters = json.loads(topic_filters)
            geo_filter = row.geo_filter or []
            if isinstance(geo_filter, str):
                geo_filter = json.loads(geo_filter)

            statuses[row.definition_hash] = await _refresh_for_hash(
                row.definition_hash,
                row.label,
                row.user_intent,
                list(entity_refs),
                list(topic_filters),
                list(geo_filter),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("user_cards refresh failed for %s: %s",
                             row.definition_hash, exc)
            statuses[row.definition_hash] = f"error: {type(exc).__name__}"

    return statuses


@app.task(
    name="tasks.refresh_user_cards",
    bind=True,
    max_retries=0,
)
def refresh_user_cards(  # type: ignore[no-untyped-def]
    self,
    only_definition_hash: str | None = None,
) -> dict:
    """Celery entrypoint. Beat-fired daily at 01:30 UTC."""
    if not _flag("FEATURE_CARDS"):
        return {"skipped": "feature flag off"}
    return {"results": asyncio.run(_refresh_all(only_definition_hash))}


def _flag(name: str) -> bool:
    raw = os.getenv(name, "").strip().lower()
    return raw in ("1", "true", "yes", "on")
