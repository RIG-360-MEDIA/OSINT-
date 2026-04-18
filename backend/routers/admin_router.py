"""
Admin API — development-only endpoints for entity dictionary management.
Gated by require_dev_environment so they never surface in production.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from backend.database import get_db
from backend.routers.debug_router import require_dev_environment

logger = logging.getLogger(__name__)

admin_router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(require_dev_environment)],
)


class EntityCreate(BaseModel):
    canonical_name: str
    entity_type: str
    aliases: list[str] = []
    state: str | None = None
    party: str | None = None
    metadata: dict = {}


@admin_router.post("/entity")
async def add_entity(req: EntityCreate) -> dict:
    """
    Upsert an entity into entity_dictionary.
    DB trigger auto-bumps dict version → NLP workers reload within 5 min.
    No container restart required.
    """
    async with get_db() as db:
        import json as _json
        await db.execute(
            text("""
                INSERT INTO entity_dictionary
                    (canonical_name, entity_type, aliases, state, party, metadata)
                VALUES (
                    :canonical_name, :entity_type, :aliases,
                    :state, :party, CAST(:metadata AS jsonb)
                )
                ON CONFLICT (canonical_name) DO UPDATE SET
                    entity_type = EXCLUDED.entity_type,
                    aliases     = EXCLUDED.aliases,
                    state       = EXCLUDED.state,
                    party       = EXCLUDED.party,
                    metadata    = EXCLUDED.metadata
            """),
            {
                "canonical_name": req.canonical_name,
                "entity_type":    req.entity_type,
                "aliases":        req.aliases,
                "state":          req.state,
                "party":          req.party,
                "metadata":       _json.dumps(req.metadata) if req.metadata else "{}",
            },
        )
        await db.commit()

        v = (await db.execute(
            text("SELECT version, entry_count FROM entity_dict_meta WHERE id = 1")
        )).fetchone()

        logger.info(
            "Entity added/updated: %s (dict v%s)",
            req.canonical_name,
            v.version if v else "?",
        )

        return {
            "success": True,
            "canonical_name": req.canonical_name,
            "dict_version":   v.version if v else None,
            "message": (
                "Entity added. NLP workers will reload within 5 min. "
                "No restart required."
            ),
        }


@admin_router.get("/entity/search")
async def search_entity(q: str) -> dict:
    """Search entity dictionary by name or alias (case-insensitive, partial match)."""
    async with get_db() as db:
        rows = (await db.execute(
            text("""
                SELECT canonical_name, entity_type, aliases, state, party
                FROM entity_dictionary
                WHERE canonical_name ILIKE :q
                   OR :q ILIKE ANY(aliases::text[])
                ORDER BY canonical_name
                LIMIT 10
            """),
            {"q": f"%{q}%"},
        )).fetchall()

        return {
            "results": [
                {
                    "canonical_name": r.canonical_name,
                    "entity_type":    r.entity_type,
                    "aliases":        r.aliases or [],
                    "state":          r.state,
                    "party":          r.party,
                }
                for r in rows
            ],
            "count": len(rows),
        }
