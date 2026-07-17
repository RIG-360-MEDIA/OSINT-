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
_ALLOWED_EVENTS = {"new_coverage", "critical_sentiment", "spike", "high_priority_story"}
# Events the delivery engine actively fires today (via the coverage-match filter);
# 'spike' and 'high_priority_story' are accepted + stored but flagged pending.
_DELIVERING_EVENTS = {"new_coverage", "critical_sentiment"}
_MAX_WEBHOOKS_PER_ORG = 25


class WebhookCreate(BaseModel):
    url: str = Field(..., max_length=2000)
    filter: dict = Field(default_factory=dict)
    events: list[str] = Field(default_factory=lambda: ["new_coverage"])


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
    # SSRF: reject at creation (not just at delivery) — https + host must resolve to public IPs.
    from ..webhook_delivery import _ssrf_ok
    if not _ssrf_ok(url):
        raise bad_request("url must be a public https endpoint (private/loopback/link-local hosts are not allowed)")
    flt = _sanitize_filter(body.filter)
    bad = sorted({e for e in (body.events or []) if e not in _ALLOWED_EVENTS})
    if bad:
        raise bad_request(f"unknown event(s): {', '.join(bad)}; allowed: {', '.join(sorted(_ALLOWED_EVENTS))}")
    evts = [e for e in (body.events or []) if e in _ALLOWED_EVENTS] or ["new_coverage"]
    # 'critical_sentiment' is delivered via the engine's sentiment=critical filter match.
    if "critical_sentiment" in evts and "sentiment" not in flt:
        flt["sentiment"] = "critical"
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
                INSERT INTO analytics.api_webhooks (org_id, url, secret, filter, events)
                VALUES (CAST(:o AS uuid), :url, '', CAST(:flt AS jsonb), CAST(:evts AS text[]))
                RETURNING id::text AS id, is_active
            """), {"o": ctx.principal.org_id, "url": url, "flt": _json(flt), "evts": evts})).fetchone()
    secret = keymod.derive_webhook_secret(row.id, hash_secret())
    request.state.result_count = 1
    pending = sorted(set(evts) - _DELIVERING_EVENTS)
    return ok({
        "id": row.id,
        "url": url,
        "filter": flt,
        "events": evts,
        "events_pending": pending or None,  # accepted but detectors still rolling out
        "is_active": bool(row.is_active),
        "secret": secret,  # shown once; recomputed at delivery, never stored
    })


@router.get("/webhooks", summary="List your webhook subscriptions")
async def list_webhooks(request: Request, ctx: ApiContext = Depends(get_context)) -> dict:
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT id::text AS id, url, filter, events, is_active, created_at, last_delivered_at
              FROM analytics.api_webhooks
             WHERE org_id = CAST(:o AS uuid)
             ORDER BY created_at DESC
        """), {"o": ctx.principal.org_id})).fetchall()
    request.state.result_count = len(rows)
    return ok([{
        "id": r.id,
        "url": r.url,
        "filter": r.filter,
        "events": list(r.events) if r.events else ["new_coverage"],
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
