"""
Seed synthetic Telangana CM test user for P07 relevance scoring verification.
Idempotent — safe to run multiple times (ON CONFLICT DO NOTHING on all inserts).
"""
from __future__ import annotations

import asyncio
import json
from datetime import time as dtime

from sqlalchemy import text

from backend.database import get_db

USER_EMAIL = "test-cm@rig-surveillance.dev"

SIGNAL_PRIORITIES = {
    "POLITICS": 9,
    "GOVERNANCE": 9,
    "INFRASTRUCTURE": 8,
    "SECURITY": 6,
    "HEALTH": 5,
    "LEGAL": 5,
    "BUSINESS": 3,
    "FINANCE": 3,
    "INTERNATIONAL": 4,
    "TECHNOLOGY": 4,
    "AGRICULTURE": 7,
    "ENVIRONMENT": 5,
    "SOCIAL": 4,
    "SPORTS": 1,
    "OTHER": 2,
}

ROLE_CONTEXT = (
    "Chief Minister of Telangana state government. "
    "Monitors governance, scheme implementation, opposition activity, "
    "district administration, and infrastructure development across "
    "all 33 Telangana districts."
)

WATCHED_ENTITIES = [
    {
        "canonical_name": "A. Revanth Reddy",
        "entity_type": "person",
        "priority": 10,
        "why_watching": "Current Chief Minister, monitor all coverage",
    },
    {
        "canonical_name": "Kaleshwaram Lift Irrigation Scheme",
        "entity_type": "scheme",
        "priority": 9,
        "why_watching": "Flagship irrigation project under political scrutiny",
    },
    {
        "canonical_name": "K. Chandrashekar Rao",
        "entity_type": "person",
        "priority": 9,
        "why_watching": "Former CM, main opposition leader BRS",
    },
    {
        "canonical_name": "K.T. Rama Rao",
        "entity_type": "person",
        "priority": 8,
        "why_watching": "BRS working president, key opposition figure",
    },
    {
        "canonical_name": "GHMC",
        "entity_type": "organisation",
        "priority": 7,
        "why_watching": "Greater Hyderabad Municipal Corporation, urban governance",
    },
    {
        "canonical_name": "Telangana",
        "entity_type": "place",
        "priority": 8,
        "why_watching": "Primary state of governance",
    },
    {
        "canonical_name": "Rythu Bandhu",
        "entity_type": "scheme",
        "priority": 8,
        "why_watching": "Farmer welfare scheme, politically sensitive",
    },
    {
        "canonical_name": "Hyderabad Metro Rail",
        "entity_type": "organisation",
        "priority": 6,
        "why_watching": "Key infrastructure project",
    },
    {
        "canonical_name": "Bhatti Vikramarka",
        "entity_type": "person",
        "priority": 7,
        "why_watching": "Deputy Chief Minister",
    },
    {
        "canonical_name": "BJP Telangana",
        "entity_type": "organisation",
        "priority": 5,
        "why_watching": "Opposition party in state",
    },
]


async def seed() -> None:
    async with get_db() as db:
        # ── Insert user ──────────────────────────────────────────────────────
        result = await db.execute(
            text(
                """
                INSERT INTO users (email)
                VALUES (:email)
                ON CONFLICT (email) DO NOTHING
                RETURNING id
                """
            ),
            {"email": USER_EMAIL},
        )
        row = result.fetchone()

        if row:
            user_id = str(row.id)
        else:
            # Already exists — fetch id
            existing = await db.execute(
                text("SELECT id FROM users WHERE email = :email"),
                {"email": USER_EMAIL},
            )
            user_id = str(existing.fetchone().id)

        await db.commit()

        # ── Insert user_profile ──────────────────────────────────────────────
        await db.execute(
            text(
                """
                INSERT INTO user_profiles (
                    user_id, raw_description, role_type,
                    geo_primary, geo_secondary,
                    signal_priorities, role_context,
                    brief_time, brief_timezone
                ) VALUES (
                    :user_id,
                    :raw_description,
                    :role_type,
                    :geo_primary,
                    :geo_secondary,
                    CAST(:signal_priorities AS jsonb),
                    :role_context,
                    :brief_time,
                    :brief_timezone
                )
                ON CONFLICT (user_id) DO NOTHING
                """
            ),
            {
                "user_id": user_id,
                "raw_description": ROLE_CONTEXT,
                "role_type": "government",
                "geo_primary": "Telangana",
                "geo_secondary": [
                    "Hyderabad",
                    "Nizamabad",
                    "Warangal",
                    "Karimnagar",
                ],
                "signal_priorities": json.dumps(SIGNAL_PRIORITIES),
                "role_context": ROLE_CONTEXT,
                "brief_time": dtime(6, 0, 0),
                "brief_timezone": "Asia/Kolkata",
            },
        )
        await db.commit()

        # ── Insert watched entities ──────────────────────────────────────────
        inserted = 0
        for ent in WATCHED_ENTITIES:
            r = await db.execute(
                text(
                    """
                    INSERT INTO user_entities (
                        user_id, canonical_name, entity_type,
                        priority, why_watching
                    ) VALUES (
                        :user_id, :canonical_name, :entity_type,
                        :priority, :why_watching
                    )
                    ON CONFLICT (user_id, canonical_name) DO NOTHING
                    RETURNING id
                    """
                ),
                {
                    "user_id": user_id,
                    "canonical_name": ent["canonical_name"],
                    "entity_type": ent["entity_type"],
                    "priority": ent["priority"],
                    "why_watching": ent["why_watching"],
                },
            )
            if r.fetchone():
                inserted += 1

        await db.commit()

        print(f"Test user seeded: {user_id}")
        print(
            f"Entities: {inserted} inserted or already exist "
            f"({len(WATCHED_ENTITIES) - inserted} already existed)"
        )


if __name__ == "__main__":
    asyncio.run(seed())
