"""Academic collector — research-footprint OSINT source (OpenAlex).

Given a person/org/topic keyword, returns the top scholarly works plus a derived
signal (total work count, most-cited piece, top authors + institutions). This is
the Tasking-brain 'academic' source made live for any keyword.

Free, no API key, no auth. OpenAlex asks callers to identify via `mailto` for the
polite pool, and a descriptive User-Agent. Venue lives at
`primary_location.source.display_name` in the current schema (legacy `host_venue`
kept only as a fallback).
"""
from __future__ import annotations

from collections import Counter
from typing import Any

import httpx

_WORKS = "https://api.openalex.org/works"
_MAILTO = "tdsworks@gmail.com"
_HEADERS = {"User-Agent": f"RIG-OSINT/1.0 (mailto:{_MAILTO})"}
_PER_PAGE = 8


def _venue(work: dict[str, Any]) -> str | None:
    """Publishing venue, preferring the current schema over the legacy field."""
    loc = work.get("primary_location") or {}
    source = loc.get("source") or {}
    name = source.get("display_name")
    if name:
        return name
    legacy = work.get("host_venue") or {}
    return legacy.get("display_name")


def _authors(work: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for a in work.get("authorships") or []:
        name = ((a.get("author") or {}).get("display_name") or "").strip()
        if name:
            out.append(name)
    return out


def _shape(work: dict[str, Any]) -> dict[str, Any]:
    oa = work.get("open_access") or {}
    loc = work.get("primary_location") or {}
    return {
        "title": (work.get("title") or "").strip() or None,
        "year": work.get("publication_year"),
        "venue": _venue(work),
        "authors": _authors(work)[:6],
        "cited_by_count": work.get("cited_by_count") or 0,
        "type": work.get("type"),
        "url": work.get("doi") or loc.get("landing_page_url"),
        "open_access": bool(oa.get("is_oa")),
        "pdf_url": oa.get("oa_url") or loc.get("pdf_url"),   # free full text when OA
    }


def _summarise(works: list[dict[str, Any]], total: int) -> dict[str, Any]:
    authors: Counter[str] = Counter()
    institutions: Counter[str] = Counter()
    fields: Counter[str] = Counter()
    for w in works:
        for a in w.get("authorships") or []:
            name = ((a.get("author") or {}).get("display_name") or "").strip()
            if name:
                authors[name] += 1
            for inst in a.get("institutions") or []:
                iname = (inst.get("display_name") or "").strip()
                if iname:
                    institutions[iname] += 1
        for con in (w.get("concepts") or [])[:5]:      # research fields/topics
            cname = (con.get("display_name") or "").strip()
            if cname and (con.get("score") or 0) >= 0.3:
                fields[cname] += 1
    top_work = max(works, key=lambda w: w.get("cited_by_count") or 0, default=None)
    return {
        "total_works": total,
        "shown": len(works),
        "top_authors": [n for n, _ in authors.most_common(5)],
        "top_institutions": [n for n, _ in institutions.most_common(5)],
        "top_fields": [n for n, _ in fields.most_common(6)],
        "open_access_shown": sum(1 for w in works if (w.get("open_access") or {}).get("is_oa")),
        "most_cited": _shape(top_work) if top_work else None,
    }


async def academic_lookup(q: str) -> dict[str, Any]:
    """Research footprint for a keyword. Returns partial data + error on failure."""
    q = (q or "").strip()
    if not q:
        return {"query": q, "error": "empty query (academic needs a person/org/topic keyword)"}

    out: dict[str, Any] = {"query": q, "works": [], "summary": {"total_works": 0, "shown": 0}}
    params = {"search": q, "per-page": _PER_PAGE, "mailto": _MAILTO}
    async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers=_HEADERS) as client:
        try:
            r = await client.get(_WORKS, params=params)
            if r.status_code == 200:
                data = r.json()
                works = data.get("results") or []
                total = ((data.get("meta") or {}).get("count")) or len(works)
                out["works"] = [_shape(w) for w in works]
                out["summary"] = _summarise(works, total)
            else:
                out["error"] = f"openalex http {r.status_code}"
                out["status"] = r.status_code
        except Exception as exc:
            out["error"] = type(exc).__name__
    return out
