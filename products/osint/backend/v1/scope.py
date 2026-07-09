"""The central scope gate — every /v1 data path goes through here.

An org's provisioned scope (analytics.org_api_scope) is the ONLY thing that
decides which entities/topics/regions a client can read. Leak-safety lives in
one place:
  * ``load_org_scope`` — read the org's allowed slice (absent row => empty).
  * ``effective_entity_ids`` — intersect a client's requested entities with
    what they're allowed; an empty result means "no data", never an error.
  * ``require_entity_in_scope`` — the IDOR guard for /{id} routes: an
    out-of-scope OR unknown id returns an identical 404 (no existence oracle).

Empty/absent scope is fail-safe: it yields zero rows, never the whole corpus.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Depends
from sqlalchemy import text

from db import get_db

from .auth import ApiPrincipal
from .errors import not_found
from .ratelimit import enforce_limits


@dataclass(frozen=True)
class OrgScope:
    org_id: str
    all_entities: bool
    entity_ids: tuple[str, ...]
    topics: tuple[str, ...]
    regions: tuple[str, ...]
    languages: tuple[str, ...]
    mute_terms: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    keyword_priorities: dict = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        """True when this org can see nothing (no provisioning)."""
        return not self.all_entities and not self.entity_ids and not self.topics and not self.regions


@dataclass(frozen=True)
class ApiContext:
    """What every scoped endpoint receives: who + what-they-may-see."""

    principal: ApiPrincipal
    scope: OrgScope


async def load_org_scope(db, org_id: str) -> OrgScope:
    """Read the org's provisioned scope. Missing row => empty (fail-safe)."""
    row = (await db.execute(text("""
        SELECT all_entities, entity_ids, topics, regions, languages,
               mute_terms, keywords, keyword_priorities
          FROM analytics.org_api_scope
         WHERE org_id = CAST(:o AS uuid)
    """), {"o": org_id})).fetchone()
    if row is None:
        return OrgScope(org_id, False, (), (), (), ())
    return OrgScope(
        org_id=org_id,
        all_entities=bool(row.all_entities),
        entity_ids=tuple(str(x) for x in (row.entity_ids or [])),
        topics=tuple(row.topics or []),
        regions=tuple(row.regions or []),
        languages=tuple(row.languages or []),
        mute_terms=tuple(row.mute_terms or []),
        keywords=tuple(row.keywords or []),
        keyword_priorities=dict(row.keyword_priorities or {}),
    )


def effective_entity_ids(scope: OrgScope, requested: tuple[str, ...] | list[str] | None) -> list[str]:
    """The entity ids a query may actually touch.

    * No request filter => all scoped ids (or [] if all_entities, meaning the
      caller should NOT constrain by entity at the SQL level — see note).
    * With a request filter => the intersection with the allowed set, so a
      client can never widen beyond their provisioning.

    For all_entities orgs with no request filter we return the sentinel value
    [] AND callers must check ``scope.all_entities`` to decide whether to apply
    an entity constraint at all.
    """
    allowed = set(scope.entity_ids)
    if not requested:
        return [] if scope.all_entities else list(scope.entity_ids)
    req = {str(x) for x in requested if x}
    if scope.all_entities:
        return list(req)
    return list(req & allowed)


def require_entity_in_scope(scope: OrgScope, entity_id: str) -> str:
    """IDOR guard for /{entity_id} routes. Out-of-scope/unknown => 404.

    Identical to a genuine 'not found' so a client cannot probe which entities
    exist outside their scope.
    """
    if scope.all_entities or entity_id in scope.entity_ids:
        return entity_id
    raise not_found()


def require_region_in_scope(scope: OrgScope, region: str) -> str:
    """IDOR guard for /{region} (country/district) routes."""
    if scope.all_entities or region in scope.regions:
        return region
    raise not_found()


async def get_context(principal: ApiPrincipal = Depends(enforce_limits)) -> ApiContext:
    """The one dependency every scoped endpoint declares.

    Chain: get_api_principal -> enforce_limits (rate + quota) -> load scope.
    By the time an endpoint body runs, the caller is authenticated, within
    their rate limit and quota, and their scope is loaded.
    """
    async with get_db() as db:
        scope = await load_org_scope(db, principal.org_id)
    return ApiContext(principal=principal, scope=scope)
