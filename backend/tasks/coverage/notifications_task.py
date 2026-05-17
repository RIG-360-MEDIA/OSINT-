"""
tasks.evaluate_notification_rules

Every 15 min. Iterates active rules, evaluates predicate against
articles ingested since last_evaluated_at. Writes notification_events
on matches. UNIQUE(rule_id, article_id) prevents duplicate fires.

Predicate JSON shape (Groq-parsed at rule creation):
    { entity_names: [...], topic: '...' or null,
      source_tier_min: 1|2|3, keywords: [...] }
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

logger = logging.getLogger(__name__)


async def _active_rules() -> list[dict[str, Any]]:
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT id::text, user_id::text, label, predicate, last_evaluated_at
                FROM notification_rules
                WHERE is_active = TRUE
                ORDER BY last_evaluated_at NULLS FIRST
                LIMIT 200
                """
            )
        )
        rows = result.fetchall()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "label": r.label,
            "predicate": r.predicate,
            "last_evaluated_at": r.last_evaluated_at,
        }
        for r in rows
    ]


async def _matching_articles(rule: dict[str, Any]) -> list[str]:
    pred = rule["predicate"] or {}
    if isinstance(pred, str):
        try:
            pred = json.loads(pred)
        except json.JSONDecodeError:
            pred = {}

    entity_names: list[str] = pred.get("entity_names") or []
    topic: str | None = pred.get("topic")
    source_tier_min: int = int(pred.get("source_tier_min") or 3)
    keywords: list[str] = pred.get("keywords") or []

    clauses: list[str] = ["a.is_duplicate IS NOT TRUE"]
    params: dict[str, Any] = {"min_tier": source_tier_min}

    if rule["last_evaluated_at"] is not None:
        clauses.append("a.collected_at > :since")
        params["since"] = rule["last_evaluated_at"]
    else:
        # First evaluation: limit to last hour to avoid blast.
        clauses.append("a.collected_at > NOW() - interval '1 hour'")

    clauses.append("a.source_tier <= :min_tier")

    if entity_names:
        # Match if entities_extracted JSONB contains any of these names.
        clauses.append(
            "EXISTS (SELECT 1 FROM jsonb_array_elements(a.entities_extracted) elt "
            "WHERE LOWER(elt->>'name') = ANY(:enames))"
        )
        params["enames"] = [n.lower() for n in entity_names]

    if topic:
        clauses.append("LOWER(a.topic_category) = LOWER(:topic)")
        params["topic"] = topic

    if keywords:
        clauses.append(
            "EXISTS (SELECT 1 FROM unnest(:kws) k "
            "WHERE a.title ILIKE '%' || k || '%' "
            "   OR COALESCE(a.lead_text_translated, a.lead_text_original, '') ILIKE '%' || k || '%')"
        )
        params["kws"] = keywords

    where_sql = " AND ".join(clauses)

    async with get_db() as db:
        result = await db.execute(
            text(f"SELECT a.id::text FROM articles a WHERE {where_sql} LIMIT 50"),
            params,
        )
        rows = result.fetchall()
    return [r[0] for r in rows]


async def _fire_events(rule_id: str, user_id: str, article_ids: list[str]) -> int:
    if not article_ids:
        return 0
    fired = 0
    async with get_db() as db:
        for aid in article_ids:
            try:
                await db.execute(
                    text(
                        """
                        INSERT INTO notification_events (rule_id, user_id, article_id)
                        VALUES (:r, :u, :a)
                        ON CONFLICT (rule_id, article_id) DO NOTHING
                        """
                    ),
                    {"r": rule_id, "u": user_id, "a": aid},
                )
                fired += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("notification fire failed: %s", exc)
        # Move evaluation cursor forward.
        await db.execute(
            text("UPDATE notification_rules SET last_evaluated_at = NOW() WHERE id = :r"),
            {"r": rule_id},
        )
        await db.commit()
    return fired


async def _run() -> dict[str, Any]:
    rules = await _active_rules()
    if not rules:
        return {"rules_evaluated": 0}

    total_fired = 0
    for rule in rules:
        try:
            article_ids = await _matching_articles(rule)
            total_fired += await _fire_events(rule["id"], rule["user_id"], article_ids)
        except Exception as exc:  # noqa: BLE001
            logger.exception("notification evaluator failed for %s: %s",
                             rule["id"], exc)

    return {"rules_evaluated": len(rules), "events_fired": total_fired}


def _flag(name: str) -> bool:
    raw = os.getenv(name, "").strip().lower()
    return raw in ("1", "true", "yes", "on")


@app.task(
    name="tasks.evaluate_notification_rules",
    bind=True,
    max_retries=0,
)
def evaluate_notification_rules(self) -> dict:  # type: ignore[no-untyped-def]
    if not _flag("FEATURE_NOTIFICATIONS"):
        return {"skipped": "feature flag off"}
    return asyncio.run(_run())
