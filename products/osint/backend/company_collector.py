"""Company / Legal-entity collector — official registration via GLEIF LEI.

Given an organization keyword, resolves it to a legal entity in the Global LEI
Index (GLEIF) and returns a verified profile: LEI, legal name, jurisdiction,
status, the NATIONAL registration id (e.g. an Indian CIN / Swiss UID — the pivot
key into the home company registry), legal address, legal form, ISINs, and the
CORPORATE HIERARCHY (parent + subsidiaries). Free, no auth, no key.

Fuzzy name resolution (not exact match) is the key fix — 'Windlass Steelcrafts'
resolves to 'WINDLASS STEELCRAFTS LLP'. GLEIF has no officers/directors (it is a
legal-entity registry); the returned registration id is the handle to look those
up in the national registry.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

_GLEIF = "https://api.gleif.org/api/v1"
_HDRS = {"User-Agent": "RIG-OSINT/1.0", "Accept": "application/vnd.api+json"}


def _name(node: Any) -> str | None:
    """GLEIF legalName/otherNames are {name, language} objects, not plain strings."""
    if isinstance(node, dict):
        return node.get("name")
    return node if isinstance(node, str) else None


def _profile(rec: dict[str, Any]) -> dict[str, Any]:
    """Flatten a GLEIF lei-record into the verified fields we surface."""
    attrs = rec.get("attributes", {}) or {}
    entity = attrs.get("entity", {}) or {}
    addr = entity.get("legalAddress", {}) or {}
    form = entity.get("legalForm", {}) or {}
    reg = attrs.get("registration", {}) or {}
    lines = addr.get("addressLines") or []
    if isinstance(lines, str):
        lines = [lines]
    parts = [*lines, addr.get("city"), addr.get("region"),
             addr.get("postalCode"), addr.get("country")]
    address = ", ".join(str(p) for p in parts if p) or None
    return {
        "lei": attrs.get("lei"),
        "legal_name": _name(entity.get("legalName")),
        "jurisdiction": entity.get("jurisdiction"),
        "country": addr.get("country"),
        "city": addr.get("city"),
        "address": address or None,
        "registration_id": entity.get("registeredAs"),   # national CIN/UID — the pivot key
        "legal_form": form.get("id") or form.get("other"),
        "category": entity.get("category"),
        "entity_status": entity.get("status"),
        "registration_status": reg.get("status"),
        "initial_registration": (reg.get("initialRegistrationDate") or "")[:10] or None,
        "last_update": (reg.get("lastUpdateDate") or "")[:10] or None,
        "next_renewal": (reg.get("nextRenewalDate") or "")[:10] or None,
    }


async def _get(client: httpx.AsyncClient, path: str,
               params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """One GLEIF GET; None on any non-200 (404 = 'no such relationship', normal)."""
    try:
        r = await client.get(f"{_GLEIF}{path}", params=params, headers=_HDRS)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


async def _fuzzy_candidates(client: httpx.AsyncClient, q: str) -> list[dict[str, Any]]:
    """Resolve a loose org name → candidate {name, lei} via GLEIF fuzzycompletions."""
    j = await _get(client, "/fuzzycompletions",
                   {"field": "entity.legalName", "q": q}) or {}
    out: list[dict[str, Any]] = []
    for item in (j.get("data") or []):
        name = (item.get("attributes") or {}).get("value")
        lei = (((item.get("relationships") or {}).get("lei-records") or {})
               .get("data") or {}).get("id")
        if name and lei:
            out.append({"name": name, "lei": lei})
    return out


def _pick_best(q: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Best candidate = the one whose name contains all query tokens; else first."""
    toks = [t for t in q.lower().split() if len(t) >= 2]
    for c in candidates:
        n = (c["name"] or "").lower()
        if toks and all(t in n for t in toks):
            return c
    return candidates[0] if candidates else None


async def _hierarchy(client: httpx.AsyncClient, lei: str) -> dict[str, Any]:
    """Corporate family: direct parent, ultimate parent, direct children."""
    dp, up, dc = await asyncio.gather(
        _get(client, f"/lei-records/{lei}/direct-parent"),
        _get(client, f"/lei-records/{lei}/ultimate-parent"),
        _get(client, f"/lei-records/{lei}/direct-children", {"page[size]": 15}),
    )

    def _one(j: dict[str, Any] | None) -> str | None:
        d = (j or {}).get("data")
        if isinstance(d, dict):
            return _name(((d.get("attributes") or {}).get("entity") or {}).get("legalName"))
        return None

    children = (dc or {}).get("data") or []
    total = (((dc or {}).get("meta") or {}).get("pagination") or {}).get("total")
    return {
        "direct_parent": _one(dp),
        "ultimate_parent": _one(up),
        "direct_children_count": total if total is not None else len(children),
        "direct_children": [
            _name(((c.get("attributes") or {}).get("entity") or {}).get("legalName"))
            for c in children[:10]
        ],
    }


async def company_lookup(q: str) -> dict[str, Any]:
    """Verified legal-entity profile for an org keyword. Partial on any failure."""
    q = (q or "").strip()
    if not q:
        return {"query": q, "error": "empty query (company needs an org name, e.g. Reliance Industries)"}

    out: dict[str, Any] = {"query": q, "matches": [], "profile": None,
                           "hierarchy": None, "summary": None}
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        candidates = await _fuzzy_candidates(client, q)
        # exact fallback if fuzzy returns nothing (e.g. a full legal name)
        if not candidates:
            j = await _get(client, "/lei-records",
                           {"filter[entity.legalName]": q, "page[size]": 5}) or {}
            candidates = [{"name": _name((r.get("attributes", {}).get("entity", {})
                                          .get("legalName"))), "lei": r.get("attributes", {}).get("lei")}
                          for r in (j.get("data") or [])]
        out["matches"] = candidates[:6]

        best = _pick_best(q, candidates)
        if best:
            rec = await _get(client, f"/lei-records/{best['lei']}")
            if rec and rec.get("data"):
                out["profile"] = _profile(rec["data"])
                out["hierarchy"] = await _hierarchy(client, best["lei"])

    p = out["profile"]
    h = out["hierarchy"] or {}
    out["summary"] = {
        "resolved": bool(p),
        "match_count": len(out["matches"]),
        "legal_name": p["legal_name"] if p else None,
        "lei": p["lei"] if p else None,
        "jurisdiction": p["jurisdiction"] if p else None,
        "registration_id": p["registration_id"] if p else None,
        "status": p["entity_status"] if p else None,
        "subsidiaries": h.get("direct_children_count"),
        "parent": h.get("direct_parent") or h.get("ultimate_parent"),
        # honest: GLEIF has no officers — the registration id is the pivot to them
        "officers_note": ("GLEIF has no officers/directors; use registration_id "
                          f"({p['registration_id']}) in the {p['jurisdiction']} company "
                          "registry" if p and p.get("registration_id") else None),
    }
    return out
