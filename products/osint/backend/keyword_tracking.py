"""Keyword tracking — persist a user's tracked keywords, list them, untrack.

Writes to analytics.keyword_watch (the night-desk API is analytics_user = RW on
analytics.*). The re-collect/alert-evaluation loop (Phase 5 beat job) reads
active rows here and writes analytics.keyword_alerts.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text


async def track_keyword(db, user_id: str, keyword: str, classification: dict | None,
                        perspective: str | None, days: int = 7,
                        cadence_minutes: int = 60) -> int:
    """Upsert a tracked keyword for a user; returns the watch id."""
    wid = (await db.execute(text("""
        INSERT INTO analytics.keyword_watch
            (user_id, keyword, classification, perspective, days, cadence_minutes)
        VALUES (:u, :q, CAST(:cls AS jsonb), :p, :d, :c)
        ON CONFLICT (user_id, keyword) DO UPDATE
            SET is_active = TRUE,
                classification = EXCLUDED.classification,
                perspective = EXCLUDED.perspective,
                days = EXCLUDED.days,
                cadence_minutes = EXCLUDED.cadence_minutes
        RETURNING id
    """), {"u": user_id, "q": keyword,
           "cls": json.dumps(classification) if classification else None,
           "p": perspective, "d": days, "c": cadence_minutes})).scalar()
    await db.commit()
    return int(wid)


async def untrack_keyword(db, user_id: str, keyword: str) -> bool:
    """Soft-delete (deactivate) a tracked keyword. Returns True if a row changed."""
    res = await db.execute(text("""
        UPDATE analytics.keyword_watch SET is_active = FALSE
         WHERE user_id = :u AND keyword = :q AND is_active
    """), {"u": user_id, "q": keyword})
    await db.commit()
    return (res.rowcount or 0) > 0


async def list_tracked(db, user_id: str) -> list[dict[str, Any]]:
    """List a user's active tracked keywords + unseen-alert counts."""
    rows = (await db.execute(text("""
        SELECT w.id, w.keyword, w.perspective, w.days, w.created_at,
               w.last_checked_at,
               (SELECT count(*) FROM analytics.keyword_alerts a
                 WHERE a.watch_id = w.id AND a.seen_at IS NULL) AS unseen
          FROM analytics.keyword_watch w
         WHERE w.user_id = :u AND w.is_active
         ORDER BY w.created_at DESC
    """), {"u": user_id})).fetchall()
    return [{
        "watch_id": r.id, "keyword": r.keyword, "perspective": r.perspective,
        "days": r.days, "created_at": r.created_at.isoformat() if r.created_at else None,
        "last_checked_at": r.last_checked_at.isoformat() if r.last_checked_at else None,
        "unseen_alerts": int(r.unseen or 0),
    } for r in rows]
