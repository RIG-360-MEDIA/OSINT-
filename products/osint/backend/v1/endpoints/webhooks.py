"""Webhook subscriptions — push alerts when new coverage matches a filter.

CRUD scoped strictly to the caller's org. The signing ``secret`` is generated
server-side and returned exactly once on creation (never on list). Deletes are
gated by org_id so a client can never touch another org's subscription.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from db import get_db

from .. import keys as keymod
from ..errors import bad_request, not_found, ok
from ..scope import ApiContext, get_context
from ..settings import hash_secret
from ..util import as_uuid

router = APIRouter(prefix="/v1", tags=["webhooks"])

_ALLOWED_FILTER_KEYS = {"entity", "topic", "sentiment"}
_MAX_WEBHOOKS_PER_ORG = 25


class WebhookCreate(BaseModel):
    url: str = Field(..., max_length=2000)
    filter: dict = Field(default_factory=dict)


def _sanitize_filter(raw: dict) -> dict:
    """Keep only known keys, coerce to short strings — no arbitrary payloads."""
    out: dict[str, str] = {}
    for k, v in (raw or {}).items():
        if k in _ALLOWED_FILTER_KEYS and v is not None:
            out[k] = str(v)[:120]
    return out


@router.post("/webhooks", summary="Create a webhook subscription")
async def create_webhook(body: WebhookCreate, request: Request, ctx: ApiContext = Depends(get_context)) -> dict:
    url = (body.url or "").strip()
    if not url.lower().startswith("https://"):
        raise bad_request("url must be an https:// endpoint")
    flt = _sanitize_filter(body.filter)
    async with get_db() as db:
        async with db.begin():
            count = (await db.execute(text("""
                SELECT count(*) AS n FROM analytics.api_webhooks WHERE org_id = CAST(:o AS uuid)
            """), {"o": ctx.principal.org_id})).fetchone()
            if count and int(count.n) >= _MAX_WEBHOOKS_PER_ORG:
                raise bad_request(f"webhook limit reached ({_MAX_WEBHOOKS_PER_ORG})")
            # The signing secret is DERIVED from the (immutable) id, never stored
            # in a recoverable form — so a DB read can't reveal it. We persist an
            # empty placeholder; the delivery worker recomputes the secret.
            row = (await db.execute(text("""
                INSERT INTO analytics.api_webhooks (org_id, url, secret, filter)
                VALUES (CAST(:o AS uuid), :url, '', CAST(:flt AS jsonb))
                RETURNING id::text AS id, is_active
            """), {"o": ctx.principal.org_id, "url": url, "flt": _json(flt)})).fetchone()
    secret = keymod.derive_webhook_secret(row.id, hash_secret())
    request.state.result_count = 1
    return ok({
        "id": row.id,
        "url": url,
        "filter": flt,
        "is_active": bool(row.is_active),
        "secret": secret,  # shown once; recomputed at delivery, never stored
    })


@router.get("/webhooks", summary="List your webhook subscriptions")
async def list_webhooks(request: Request, ctx: ApiContext = Depends(get_context)) -> dict:
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT id::text AS id, url, filter, is_active, created_at, last_delivered_at
              FROM analytics.api_webhooks
             WHERE org_id = CAST(:o AS uuid)
             ORDER BY created_at DESC
        """), {"o": ctx.principal.org_id})).fetchall()
    request.state.result_count = len(rows)
    return ok([{
        "id": r.id,
        "url": r.url,
        "filter": r.filter,
        "is_active": bool(r.is_active),
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "last_delivered_at": r.last_delivered_at.isoformat() if r.last_delivered_at else None,
    } for r in rows], meta={"count": len(rows)})


@router.delete("/webhooks/{webhook_id}", summary="Delete a webhook subscription")
async def delete_webhook(webhook_id: str, request: Request, ctx: ApiContext = Depends(get_context)) -> dict:
    wid = as_uuid(webhook_id)
    if wid is None:
        raise not_found()
    async with get_db() as db:
        async with db.begin():
            res = await db.execute(text("""
                DELETE FROM analytics.api_webhooks
                 WHERE id = CAST(:id AS uuid) AND org_id = CAST(:o AS uuid)
            """), {"id": wid, "o": ctx.principal.org_id})
    if res.rowcount == 0:  # missing OR another org's — identical 404
        raise not_found()
    request.state.result_count = 1
    return ok({"deleted": True, "id": wid})


def _json(obj: dict) -> str:
    import json
    return json.dumps(obj)
