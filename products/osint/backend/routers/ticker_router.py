"""GET /api/brief/ticker — the newest real Indian headlines for the Home ticker.

Powers the Night Desk "Breaking" marquee. Returns the ~20 most recently
collected India-sourced articles from the last 48h, newest first, so the
scrolling ticker shows live corpus headlines instead of hardcoded copy.

Unauthenticated by design — the marquee renders on the public home view, so we
serve real data even without a signed-in persona (no personalization here).
Non-English titles carry a `title_en` (via i18n.attach_en) only when it differs
from the original.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text

from auth.middleware import get_optional_user
from db import get_db
import i18n

router = APIRouter(prefix="/api/brief", tags=["brief"])


@router.get("/ticker")
async def get_ticker(
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    """Newest 20 Indian headlines from the last 48h (returns data even unauth)."""
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT a.id::text AS id,
                   a.title,
                   a.url,
                   s.name AS source,
                   a.collected_at AS when_ts
              FROM articles a
              JOIN sources s ON s.id = a.source_id
             WHERE a.source_country = 'IN'
               AND a.collected_at >= analytics.now_sim() - interval '48 hours'
               AND a.title IS NOT NULL AND LENGTH(a.title) > 0
             ORDER BY a.collected_at DESC
             LIMIT 20
        """))).fetchall()

        items: list[dict[str, Any]] = [{
            "id": r.id,
            "title": r.title,
            "url": r.url,
            "source": r.source,
            "when": r.when_ts.isoformat() if r.when_ts is not None else None,
        } for r in rows]

        # Translate non-English headlines in place; expose `title_en` only when
        # it actually differs from the original (attach_en skips English titles).
        await i18n.attach_en(db, items, "title")
        return {"items": items}
