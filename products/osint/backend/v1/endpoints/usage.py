"""Usage endpoint — the calling key's consumption against its quota."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text

from db import get_db

from ..errors import ok
from ..scope import ApiContext, get_context

router = APIRouter(prefix="/v1", tags=["usage"])


def _period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


@router.get("/usage", summary="Your current period usage")
async def usage(request: Request, ctx: ApiContext = Depends(get_context)) -> dict:
    key_id = ctx.principal.key_id
    quota = ctx.principal.monthly_quota
    async with get_db() as db:
        crow = (await db.execute(text("""
            SELECT request_count FROM analytics.api_usage_counters
             WHERE key_id = CAST(:k AS uuid) AND period = :p
        """), {"k": key_id, "p": _period()})).fetchone()
        requests = int(crow.request_count) if crow else 0
        by_ep = (await db.execute(text("""
            SELECT endpoint, count(*) AS n
              FROM analytics.api_usage_events
             WHERE key_id = CAST(:k AS uuid)
               AND ts >= date_trunc('month', now())
             GROUP BY endpoint ORDER BY n DESC LIMIT 15
        """), {"k": key_id})).fetchall()
    request.state.result_count = requests
    return ok({
        "period": _period(),
        "requests": requests,
        "quota": quota,
        "remaining": (max(0, quota - requests) if quota is not None else None),
        "by_endpoint": [{"endpoint": r.endpoint, "requests": int(r.n)} for r in by_ep],
    })
