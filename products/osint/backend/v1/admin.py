"""Staff-only key + scope administration for the /v1 gateway.

These endpoints ISSUE / LIST / REVOKE API keys and PROVISION an org's data
scope. They are protected by the JWT dashboard auth (``require_super_admin``)
— NOT by an API key — so a client can never mint or widen their own access.
The raw key is returned exactly once, at creation, and never again.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text

from auth.middleware import require_super_admin
from db import get_db

from . import keys as keymod
from .errors import bad_request, not_found, ok
from .settings import DEFAULT_RATE_LIMIT_PER_MIN, hash_secret
from .util import as_uuid

router = APIRouter(prefix="/v1/admin", tags=["admin"])


# ── Keys ────────────────────────────────────────────────────────────────────

class KeyCreate(BaseModel):
    org_id: str
    label: str = Field("", max_length=120)
    sandbox: bool = False
    rate_limit_per_min: int = Field(DEFAULT_RATE_LIMIT_PER_MIN, ge=1, le=100000)
    monthly_quota: int | None = Field(None, ge=1)
    expires_at: str | None = None  # ISO 8601, optional


@router.post("/keys", summary="Issue a new API key (shown once)")
async def create_key(body: KeyCreate, principal: dict = Depends(require_super_admin)) -> dict:
    org_id = as_uuid(body.org_id)
    if org_id is None:
        raise bad_request("org_id must be a valid uuid")
    raw = keymod.generate_key(sandbox=body.sandbox)
    params = {
        "o": org_id,
        "h": keymod.hash_key(raw, hash_secret()),
        "pfx": keymod.prefix_of(raw),
        "label": body.label or "",
        "sb": body.sandbox,
        "rl": body.rate_limit_per_min,
        "mq": body.monthly_quota,
        "cb": principal["id"],
        "exp": body.expires_at or None,
    }
    async with get_db() as db:
        async with db.begin():
            org = (await db.execute(text(
                "SELECT 1 FROM analytics.orgs WHERE id = CAST(:o AS uuid)"
            ), {"o": org_id})).fetchone()
            if org is None:
                raise not_found("org not found")
            row = (await db.execute(text("""
                INSERT INTO analytics.api_keys
                    (org_id, key_hash, key_prefix, label, is_sandbox,
                     rate_limit_per_min, monthly_quota, created_by, expires_at)
                VALUES
                    (CAST(:o AS uuid), :h, :pfx, :label, :sb,
                     :rl, :mq, CAST(:cb AS uuid), CAST(:exp AS timestamptz))
                RETURNING id::text AS id, created_at
            """), params)).fetchone()
    return ok({
        "id": row.id,
        "key": raw,  # shown ONCE
        "key_prefix": params["pfx"],
        "org_id": org_id,
        "is_sandbox": body.sandbox,
        "rate_limit_per_min": body.rate_limit_per_min,
        "monthly_quota": body.monthly_quota,
        "warning": "Store this key now — it cannot be retrieved again.",
    })


@router.get("/keys", summary="List an org's keys (no secrets)")
async def list_keys(org_id: str, principal: dict = Depends(require_super_admin)) -> dict:
    oid = as_uuid(org_id)
    if oid is None:
        raise bad_request("org_id must be a valid uuid")
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT id::text AS id, key_prefix, label, is_sandbox,
                   rate_limit_per_min, monthly_quota,
                   created_at, last_used_at, revoked_at, expires_at
              FROM analytics.api_keys
             WHERE org_id = CAST(:o AS uuid)
             ORDER BY created_at DESC
        """), {"o": oid})).fetchall()
    return ok([{
        "id": r.id,
        "key_prefix": r.key_prefix,
        "label": r.label,
        "is_sandbox": bool(r.is_sandbox),
        "rate_limit_per_min": r.rate_limit_per_min,
        "monthly_quota": r.monthly_quota,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
        "revoked": r.revoked_at is not None,
        "expires_at": r.expires_at.isoformat() if r.expires_at else None,
    } for r in rows], meta={"count": len(rows)})


@router.post("/keys/{key_id}/revoke", summary="Revoke a key immediately")
async def revoke_key(key_id: str, principal: dict = Depends(require_super_admin)) -> dict:
    kid = as_uuid(key_id)
    if kid is None:
        raise not_found()
    async with get_db() as db:
        async with db.begin():
            res = await db.execute(text("""
                UPDATE analytics.api_keys SET revoked_at = now()
                 WHERE id = CAST(:k AS uuid) AND revoked_at IS NULL
            """), {"k": kid})
    return ok({"id": kid, "revoked": True, "was_already_revoked": res.rowcount == 0})


# ── Scope provisioning ──────────────────────────────────────────────────────

class ScopeUpdate(BaseModel):
    all_entities: bool = False
    entity_ids: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)


@router.put("/scope/{org_id}", summary="Set an org's provisioned data scope")
async def set_scope(org_id: str, body: ScopeUpdate, principal: dict = Depends(require_super_admin)) -> dict:
    oid = as_uuid(org_id)
    if oid is None:
        raise bad_request("org_id must be a valid uuid")
    entity_ids: list[str] = []
    for e in body.entity_ids:
        v = as_uuid(e)
        if v is None:
            raise bad_request(f"entity_ids contains a non-uuid value: {e!r}")
        entity_ids.append(v)
    topics = [str(t).strip()[:80] for t in body.topics if str(t).strip()]
    regions = [str(r).strip()[:80] for r in body.regions if str(r).strip()]
    languages = [str(x).strip()[:8] for x in body.languages if str(x).strip()]
    async with get_db() as db:
        async with db.begin():
            org = (await db.execute(text(
                "SELECT 1 FROM analytics.orgs WHERE id = CAST(:o AS uuid)"
            ), {"o": oid})).fetchone()
            if org is None:
                raise not_found("org not found")
            await db.execute(text("""
                INSERT INTO analytics.org_api_scope
                    (org_id, all_entities, entity_ids, topics, regions, languages, updated_at)
                VALUES
                    (CAST(:o AS uuid), :ae, CAST(:eids AS uuid[]), :topics, :regions, :langs, now())
                ON CONFLICT (org_id) DO UPDATE SET
                    all_entities = EXCLUDED.all_entities,
                    entity_ids   = EXCLUDED.entity_ids,
                    topics       = EXCLUDED.topics,
                    regions      = EXCLUDED.regions,
                    languages    = EXCLUDED.languages,
                    updated_at   = now()
            """), {
                "o": oid, "ae": body.all_entities, "eids": entity_ids,
                "topics": topics, "regions": regions, "langs": languages,
            })
    return ok({
        "org_id": oid,
        "all_entities": body.all_entities,
        "entity_ids": entity_ids,
        "topics": topics,
        "regions": regions,
        "languages": languages,
    })


@router.get("/scope/{org_id}", summary="Read an org's provisioned scope")
async def get_scope_admin(org_id: str, principal: dict = Depends(require_super_admin)) -> dict:
    oid = as_uuid(org_id)
    if oid is None:
        raise bad_request("org_id must be a valid uuid")
    async with get_db() as db:
        row = (await db.execute(text("""
            SELECT all_entities, entity_ids, topics, regions, languages, updated_at
              FROM analytics.org_api_scope WHERE org_id = CAST(:o AS uuid)
        """), {"o": oid})).fetchone()
    if row is None:
        return ok({"org_id": oid, "all_entities": False, "entity_ids": [],
                   "topics": [], "regions": [], "languages": [], "provisioned": False})
    return ok({
        "org_id": oid,
        "all_entities": bool(row.all_entities),
        "entity_ids": [str(x) for x in (row.entity_ids or [])],
        "topics": list(row.topics or []),
        "regions": list(row.regions or []),
        "languages": list(row.languages or []),
        "provisioned": True,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    })
