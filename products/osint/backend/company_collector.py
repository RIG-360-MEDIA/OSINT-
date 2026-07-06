"""Company / Legal-entity collector — official registration lookup via GLEIF LEI.

Given an organization keyword, returns matched legal entities from the Global LEI
Index (GLEIF): LEI code, legal name, jurisdiction, legal address, legal form, and
registration status. Free, no auth, no key. This is the Tasking-brain 'company'
source made live for org keywords (e.g. "Reliance Industries" -> LEI + jurisdiction).
"""
from __future__ import annotations

from typing import Any

import httpx

_GLEIF = "https://api.gleif.org/api/v1/lei-records"


def _name(node: Any) -> str | None:
    """GLEIF legalName/otherNames are {name, language} objects, not plain strings."""
    if isinstance(node, dict):
        return node.get("name")
    return node if isinstance(node, str) else None


def _parse_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Flatten one GLEIF lei-record into the fields we surface. Never raises."""
    attrs = rec.get("attributes", {}) or {}
    entity = attrs.get("entity", {}) or {}
    addr = entity.get("legalAddress", {}) or {}
    form = entity.get("legalForm", {}) or {}
    reg = attrs.get("registration", {}) or {}
    return {
        "lei": attrs.get("lei"),
        "legal_name": _name(entity.get("legalName")),
        "jurisdiction": entity.get("jurisdiction"),
        "country": addr.get("country"),
        "city": addr.get("city"),
        "legal_form": form.get("id") or form.get("other"),
        "entity_status": entity.get("status"),
        "registration_status": reg.get("status"),
    }


async def company_lookup(q: str) -> dict[str, Any]:
    """Legal-entity registration profile for an org keyword. Partial on any failure."""
    q = (q or "").strip()
    if not q:
        return {"query": q, "error": "empty query (company needs an org name, e.g. Reliance Industries)"}

    out: dict[str, Any] = {"query": q, "matches": [], "summary": None}
    params = {"filter[entity.legalName]": q, "page[size]": 5}
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        try:
            r = await client.get(_GLEIF, params=params)
            if r.status_code == 200:
                data = r.json().get("data", []) or []
                out["matches"] = [_parse_record(rec) for rec in data]
            else:
                out["gleif_status"] = r.status_code
        except Exception as exc:
            out["gleif_error"] = type(exc).__name__

    # derived signal: the top match, its jurisdiction and registration lifecycle
    matches = out["matches"]
    top = matches[0] if matches else None
    out["summary"] = {
        "found": len(matches),
        "top_lei": top["lei"] if top else None,
        "top_name": top["legal_name"] if top else None,
        "jurisdiction": top["jurisdiction"] if top else None,
        "registration_status": top["registration_status"] if top else None,
    }
    return out
