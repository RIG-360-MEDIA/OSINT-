"""Client-facing scope self-management.

- GET  /v1/scope        — read your org's scope (any key).
- PATCH /v1/scope       — add/remove entities/topics/keywords/regions/languages/mute_terms
                          and set keyword priorities (requires a management-capable key).
- POST /v1/scope/purge  — explicit, confirmed purge of your scope + webhooks (no auto-cascade).

The corpus is the shared news feed; scope is a per-org FILTER over it, not a data boundary
(so a client managing its own scope can't reach another client's data). The caps here are
commercial guardrails, not a security boundary. Only keys with can_manage=true may write.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from db import get_db

from .. import queries
from ..errors import bad_request, forbidden, ok
from ..scope import ApiContext, get_context
from ..util import as_uuid

router = APIRouter(prefix="/v1", tags=["scope"])

_CAPS = {"entity_ids": 500, "keywords": 200, "mute_terms": 100, "topics": 50, "regions": 50, "languages": 20}


def _require_manage(ctx: ApiContext) -> None:
    if not ctx.principal.can_manage:
        raise forbidden("this key is not permitted to manage scope")


def _apply(cur: list, add: list, remove: list, *, lower: bool = False, maxlen: int = 120) -> list:
    norm = (lambda x: x.lower()) if lower else (lambda x: x)
    rem = {norm(str(x)) for x in remove}
    out = [x for x in cur if norm(x) not in rem]
    seen = {norm(x) for x in out}
    for a in add:
        a = str(a).strip()[:maxlen]
        if a and norm(a) not in seen:
            out.append(a)
            seen.add(norm(a))
    return out


class ScopePatch(BaseModel):
    add_entities: list[str] = Field(default_factory=list)
    remove_entities: list[str] = Field(default_factory=list)
    add_topics: list[str] = Field(default_factory=list)
    remove_topics: list[str] = Field(default_factory=list)
    add_keywords: list[str] = Field(default_factory=list)
    remove_keywords: list[str] = Field(default_factory=list)
    add_regions: list[str] = Field(default_factory=list)
    remove_regions: list[str] = Field(default_factory=list)
    add_mute_terms: list[str] = Field(default_factory=list)
    remove_mute_terms: list[str] = Field(default_factory=list)
    languages: list[str] | None = None          # replace when provided
    keyword_priorities: dict | None = None       # merge when provided


def _view(all_entities, entity_ids, topics, keywords, regions, languages, mute_terms, kp) -> dict:
    return {
        "all_entities": all_entities, "entity_ids": list(entity_ids), "topics": list(topics),
        "keywords": list(keywords), "regions": list(regions), "languages": list(languages),
        "mute_terms": list(mute_terms), "keyword_priorities": dict(kp),
    }


@router.get("/scope", summary="Read your org's provisioned scope")
async def read_scope(request: Request, ctx: ApiContext = Depends(get_context)) -> dict:
    s = ctx.scope
    request.state.result_count = 1
    return ok({**_view(s.all_entities, s.entity_ids, s.topics, s.keywords, s.regions,
                        s.languages, s.mute_terms, s.keyword_priorities),
               "can_manage": ctx.principal.can_manage})


@router.patch("/scope", summary="Manage your scope (management key required)")
async def patch_scope(body: ScopePatch, request: Request, ctx: ApiContext = Depends(get_context)) -> dict:
    _require_manage(ctx)
    s = ctx.scope

    # add_entities accepts a UUID *or* a display name. Adding to scope is the act of
    # bringing a new entity in, so a name is resolved against the FULL entity dictionary
    # (not scope-restricted). A name that matches no known entity is never rejected — it
    # falls back to a free-text keyword, so nothing the client asks to track is dropped.
    add_e: list[str] = []
    resolved_names: list[dict] = []
    name_fallback_keywords: list[str] = []
    async with get_db() as db:
        for e in body.add_entities:
            v = as_uuid(e)
            if v is not None:
                add_e.append(v)
                continue
            name = str(e).strip()
            if not name:
                continue
            rid = await queries.resolve_entity_by_name(db, name, [], all_entities=True)
            if rid is not None:
                add_e.append(rid)
                resolved_names.append({"name": name, "entity_id": rid})
            else:
                name_fallback_keywords.append(name)

    entity_ids = _apply(list(s.entity_ids), add_e, body.remove_entities)
    topics = _apply(list(s.topics), body.add_topics, body.remove_topics)
    keywords = _apply(list(s.keywords), list(body.add_keywords) + name_fallback_keywords,
                      body.remove_keywords, lower=True)
    regions = _apply(list(s.regions), body.add_regions, body.remove_regions)
    mute_terms = _apply(list(s.mute_terms), body.add_mute_terms, body.remove_mute_terms, lower=True)
    languages = ([str(x).strip()[:8] for x in body.languages if str(x).strip()]
                 if body.languages is not None else list(s.languages))
    kp = dict(s.keyword_priorities)
    if body.keyword_priorities is not None:
        for k, v in body.keyword_priorities.items():
            try:
                kp[str(k).strip().lower()[:120]] = int(v)
            except (TypeError, ValueError):
                pass

    for name, val in (("entity_ids", entity_ids), ("keywords", keywords), ("mute_terms", mute_terms),
                      ("topics", topics), ("regions", regions), ("languages", languages)):
        if len(val) > _CAPS[name]:
            raise bad_request(f"{name} exceeds the plan limit ({_CAPS[name]})")

    async with get_db() as db:
        async with db.begin():
            await db.execute(text("""
                INSERT INTO analytics.org_api_scope
                    (org_id, all_entities, entity_ids, topics, regions, languages,
                     mute_terms, keywords, keyword_priorities, updated_at)
                VALUES (CAST(:o AS uuid), :ae, CAST(:eids AS uuid[]), :topics, :regions, :langs,
                        :mutes, :kw, CAST(:kp AS jsonb), now())
                ON CONFLICT (org_id) DO UPDATE SET
                    entity_ids=EXCLUDED.entity_ids, topics=EXCLUDED.topics, regions=EXCLUDED.regions,
                    languages=EXCLUDED.languages, mute_terms=EXCLUDED.mute_terms,
                    keywords=EXCLUDED.keywords, keyword_priorities=EXCLUDED.keyword_priorities, updated_at=now()
            """), {"o": ctx.principal.org_id, "ae": s.all_entities, "eids": entity_ids, "topics": topics,
                   "regions": regions, "langs": languages, "mutes": mute_terms, "kw": keywords,
                   "kp": json.dumps(kp)})
    request.state.result_count = 1
    out = _view(s.all_entities, entity_ids, topics, keywords, regions, languages, mute_terms, kp)
    if resolved_names:
        out["resolved_entities"] = resolved_names
    if name_fallback_keywords:
        out["added_as_keywords"] = name_fallback_keywords
    return ok(out)


class PurgeBody(BaseModel):
    confirm: bool = False


@router.post("/scope/purge", summary="Explicitly purge your scope + webhooks (confirm required)")
async def purge_scope(body: PurgeBody, request: Request, ctx: ApiContext = Depends(get_context)) -> dict:
    _require_manage(ctx)
    if not body.confirm:
        raise bad_request("purge requires confirm=true — it stops all tracking for your org (no auto-cascade)")
    async with get_db() as db:
        async with db.begin():
            await db.execute(text("""
                UPDATE analytics.org_api_scope
                   SET entity_ids='{}', topics='{}', regions='{}', languages='{}',
                       mute_terms='{}', keywords='{}', keyword_priorities='{}'::jsonb, updated_at=now()
                 WHERE org_id=CAST(:o AS uuid)
            """), {"o": ctx.principal.org_id})
            await db.execute(text("UPDATE analytics.api_webhooks SET is_active=false WHERE org_id=CAST(:o AS uuid)"),
                             {"o": ctx.principal.org_id})
    request.state.result_count = 1
    return ok({"purged": True,
               "note": "scope cleared + webhooks deactivated; the shared stored corpus is unaffected"})
