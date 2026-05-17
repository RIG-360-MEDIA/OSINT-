"""
tasks.spawn_sub_cards

Once per newly-created parent user_card, derives 3-5 "intelligence
sub-cards" — each its own mini-tracker with a unique analytical angle.

The sub-cards are not predicates the user explicitly asked for; they
are inferred from the user's free-text description. Examples for a
political-action card might include:
    - "Threats to <subject>'s position"
    - "What <subject> should be watching"
    - "Counter-narrative the opposition is pushing"
    - "Allies and aligned moves"

Each sub-card row is inserted in user_cards with parent_card_id set,
its own derived entity_refs / topic_filters predicate, and its own
sub_card_angle label. Subsequent refresh_user_cards runs will pick
them up via the same definition_hash flow as parent cards.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
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


_SPAWN_SYSTEM = (
    "You are an intelligence analyst. The user has created a TRACKER CARD "
    "with a label and a description of what they want to follow. Your job: "
    "derive 3-5 sub-trackers — distinct ANALYTICAL ANGLES on the same "
    "subject that this user would value but didn't explicitly state.\n\n"
    "Each sub-tracker should be a unique lens (NOT a paraphrase of the "
    "parent). Examples of good lenses for political-figure tracking: "
    "'Threats to subject's position', 'What subject should be watching', "
    "'Counter-narrative opposition is pushing', 'Allies and aligned moves', "
    "'Developing news in subject's interest area'. For a topic tracker "
    "(infrastructure, policy etc.), good lenses are 'Funding decisions', "
    "'Implementation timelines', 'Stakeholder reactions', 'Risks to "
    "delivery', 'Comparable past projects'.\n\n"
    "Return STRICT JSON, no fences:\n"
    "{ \"sub_cards\": [\n"
    "  { \"angle\": \"<short, decisive lens label, max 8 words>\",\n"
    "    \"reasoning\": \"<one sentence describing what this lens "
    "watches for, will be saved as that sub-card's user_intent>\",\n"
    "    \"entity_refs\": [\"name1\", \"name2\", ...] (lowercased canonical "
    "entity names; max 8),\n"
    "    \"topic_filters\": [\"POLITICS\"|\"GOVERNANCE\"|\"SECURITY\"|"
    "\"LEGAL\"|\"INFRASTRUCTURE\"|\"HEALTH\"|\"FINANCE\"|\"BUSINESS\"|"
    "\"INTERNATIONAL\"|\"ENVIRONMENT\"|\"AGRICULTURE\"|\"SOCIAL\"|\"OTHER\"] "
    "(0-3 categories) }\n"
    "  , ... 3 to 5 entries total ]\n"
    "}\n"
    "Rules:\n"
    "- ANGLES must be distinct from each other (no two looking at the same "
    "  thing). Cover different vantages: defensive, offensive, "
    "  geographic, temporal, narrative.\n"
    "- entity_refs MUST overlap with the parent's stated subject (so the "
    "  sub-card actually pulls articles relevant to the parent), but each "
    "  may add 1-3 angle-specific entities (e.g. for 'Threats to X', add "
    "  the named opposition).\n"
    "- topic_filters: pick categories the lens actually wants. Empty array "
    "  is fine when the lens is entity-driven."
)


def _hash_predicate(
    entity_refs: list[str],
    topic_filters: list[str],
    geo_filter: list[str],
) -> str:
    """Same shape as the parent-card definition_hash used elsewhere."""
    payload = json.dumps(
        {
            "entities": sorted(entity_refs),
            "topics": sorted(topic_filters),
            "geo": sorted(geo_filter),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _spawn_for_parent(parent_id: str) -> dict[str, Any]:
    async with get_db() as db:
        r = await db.execute(
            text(
                """
                SELECT id::text, user_id::text, label, user_intent,
                       entity_refs, topic_filters, geo_filter,
                       sub_cards_spawned
                FROM user_cards
                WHERE id = :id AND parent_card_id IS NULL
                """
            ),
            {"id": parent_id},
        )
        parent = r.fetchone()

    if not parent:
        return {"error": "parent not found"}
    if parent.sub_cards_spawned:
        return {"skipped": "already spawned"}

    parent_entities = parent.entity_refs or []
    if isinstance(parent_entities, str):
        parent_entities = json.loads(parent_entities)
    parent_topics = parent.topic_filters or []
    if isinstance(parent_topics, str):
        parent_topics = json.loads(parent_topics)
    parent_geo = parent.geo_filter or []
    if isinstance(parent_geo, str):
        parent_geo = json.loads(parent_geo)

    user_prompt = (
        f"Parent label: {parent.label}\n\n"
        f"Parent description (user intent):\n{parent.user_intent or '(none)'}\n\n"
        f"Parent entity_refs (already tracked): {parent_entities}\n\n"
        "Return the JSON described in the system prompt."
    )

    try:
        raw = await call_groq(
            system=_SPAWN_SYSTEM,
            user=user_prompt,
            task_type="rag_response",
            model=QUALITY_MODEL,
            json_response=True,
        )
        parsed = json.loads(raw)
    except (GroqQuotaExhausted, GroqCallFailed) as exc:
        logger.warning("spawn_sub_cards Groq failed for %s: %s", parent_id, exc)
        return {"error": "groq failed"}
    except json.JSONDecodeError:
        logger.warning("spawn_sub_cards non-JSON for %s", parent_id)
        return {"error": "json parse"}

    sub_cards = parsed.get("sub_cards") if isinstance(parsed, dict) else None
    if not isinstance(sub_cards, list) or not sub_cards:
        return {"error": "no sub-cards in response"}

    inserted = 0
    async with get_db() as db:
        for sc in sub_cards[:5]:
            angle = str(sc.get("angle") or "").strip()[:120]
            reasoning = str(sc.get("reasoning") or "").strip()[:600]
            ents = sc.get("entity_refs") or []
            if isinstance(ents, str):
                ents = [ents]
            ents = [str(e).strip().lower()[:120] for e in ents if e][:8]
            # Sub-card MUST share at least one entity with parent so it
            # pulls actually-related articles. If Groq forgot, splice
            # parent entities in.
            if not any(e in parent_entities for e in ents):
                ents = (ents + list(parent_entities))[:8]

            topics = sc.get("topic_filters") or []
            if isinstance(topics, str):
                topics = [topics]
            topics = [str(t).strip().upper()[:30] for t in topics if t][:3]

            if not angle or not ents:
                continue

            geo = list(parent_geo)  # inherit parent geo
            d_hash = _hash_predicate(ents, topics, geo)

            await db.execute(
                text(
                    """
                    INSERT INTO user_cards
                      (user_id, label, definition_hash,
                       entity_refs, topic_filters, geo_filter,
                       user_intent,
                       parent_card_id, sub_card_angle,
                       sub_cards_spawned)
                    VALUES
                      (CAST(:uid AS uuid), :lbl, :hash,
                       CAST(:ents AS jsonb), CAST(:topics AS jsonb),
                       CAST(:geo AS jsonb),
                       :intent,
                       CAST(:parent AS uuid), :angle,
                       TRUE)
                    """
                ),
                {
                    "uid": parent.user_id,
                    "lbl": angle,  # sub-card "label" IS its angle
                    "hash": d_hash,
                    "ents": json.dumps(ents),
                    "topics": json.dumps(topics),
                    "geo": json.dumps(geo),
                    "intent": reasoning,
                    "parent": parent_id,
                    "angle": angle,
                },
            )
            inserted += 1

        # Mark parent done.
        await db.execute(
            text(
                "UPDATE user_cards SET sub_cards_spawned = TRUE "
                "WHERE id = CAST(:id AS uuid)"
            ),
            {"id": parent_id},
        )
        await db.commit()

    # Trigger immediate refresh on parent + all sub-cards so the
    # detail view has data on first open.
    try:
        app.send_task(
            "tasks.refresh_user_cards",
            kwargs={},  # broad refresh — picks up new children naturally
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("post-spawn refresh fan-out failed: %s", exc)

    return {"parent_id": parent_id, "spawned": inserted}


@app.task(
    name="tasks.spawn_sub_cards",
    bind=True,
    max_retries=2,
)
def spawn_sub_cards(  # type: ignore[no-untyped-def]
    self, parent_card_id: str
) -> dict:
    """One-shot, fired by the card-create endpoint."""
    return asyncio.run(_spawn_for_parent(parent_card_id))
