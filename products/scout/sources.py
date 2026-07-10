"""Scout sources — one keyword, every keyword-capable source, in parallel, FULL records.

Design rules (from the product owner):
  - Each source stays in its OWN envelope (its native fields, nothing trimmed).
  - Newest-first WITHIN a source. No ranking ACROSS sources, no dedup (later phase).
  - Honest per-source ok/error/note — never a silent empty (a blocked source SAYS so).

Everything is called IN-PROCESS (the collectors are plain async funcs). Social needs the
session cookies (loaded from .env by app.py); SearXNG needs rig-searxng (box-only — fails
honestly off-box). Identity footprint + domain/country sources (infra/archive/stats) are
NOT keyword-native and are added in a later step.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable

from backend.collectors.cheap_stack.keyword_search import REGISTRY as SOCIAL
from products.osint.backend.academic_collector import academic_lookup
from products.osint.backend.company_collector import company_lookup
from products.osint.backend.gdelt_collector import gdelt_coverage
from products.osint.backend.geo_collector import geo_lookup
from products.osint.backend.news_collector import news_search
from products.osint.backend.searxng_collector import web_search
from products.osint.backend.tender_collector import tender_search
from products.osint.backend.wiki_collector import wiki_lookup

PER_SOURCE_TIMEOUT = 20.0


@dataclass
class SourceResult:
    name: str
    group: str                 # "social" | "osint"
    ok: bool
    count: int
    items: list[dict]          # full records — every field kept
    meta: dict                 # source-level extras (summary/infobox/hierarchy/...)
    note: str | None
    error: str | None
    elapsed_s: float


def _sort_newest(items: list[dict], date_key: str | None) -> list[dict]:
    if not date_key:
        return items
    try:
        return sorted(items, key=lambda it: str(it.get(date_key) or ""), reverse=True)
    except Exception:
        return items


async def _guard(name: str, group: str, factory: Callable[[], Any],
                 extract: Callable[[Any], tuple], date_key: str | None,
                 timeout: float) -> SourceResult:
    """Run one source with its own timeout; turn any failure into an honest envelope."""
    t0 = time.monotonic()
    try:
        raw = await asyncio.wait_for(factory(), timeout=timeout)
    except asyncio.TimeoutError:
        return SourceResult(name, group, False, 0, [], {}, None,
                            f"slow — no response in {timeout:.0f}s (source is up, just slow here)",
                            round(time.monotonic() - t0, 1))
    except Exception as exc:
        return SourceResult(name, group, False, 0, [], {},
                            None, f"{type(exc).__name__}: {exc}"[:180], round(time.monotonic() - t0, 1))
    ok, items, meta, note, error = extract(raw)
    items = _sort_newest(list(items or []), date_key)
    return SourceResult(name, group, bool(ok), len(items), items, meta or {}, note, error,
                        round(time.monotonic() - t0, 1))


# ── extractors: pull the FULL records + source-level meta out of each raw result ──

def _ex_social(r: Any) -> tuple:
    return (bool(getattr(r, "ok", False)), list(getattr(r, "posts", ()) or ()),
            {"method": getattr(r, "method", None)}, getattr(r, "note", None), getattr(r, "error", None))


def _ex_news(r: dict) -> tuple:
    return (True, r.get("articles") or [], {"summary": r.get("summary")}, None, r.get("error"))


def _ex_web(r: dict) -> tuple:
    return (True, r.get("results") or [],
            {"infobox": r.get("infobox"), "summary": r.get("summary"),
             "top_sources": r.get("top_sources"), "suggestions": r.get("suggestions")}, r.get("_note"), None)


async def _web_call(kw: str, lim: int) -> dict:
    """SearXNG is internal-only (rig-searxng) — off-box this fails; say so, don't error."""
    try:
        return await web_search(kw, limit=lim)
    except Exception:
        return {"results": [], "_note": "SearXNG is server-only — web results appear when Scout runs on the box"}


def _ex_company(r: dict) -> tuple:
    prof, matches = r.get("profile"), r.get("matches") or []
    items = [prof] if prof else matches
    return (True, items, {"hierarchy": r.get("hierarchy"), "summary": r.get("summary")},
            (r.get("summary") or {}).get("officers_note"), None)


def _ex_academic(r: dict) -> tuple:
    return (True, r.get("works") or [], {"summary": r.get("summary")}, None, None)


def _ex_gdelt(r: dict) -> tuple:
    return (True, r.get("articles") or [], {"summary": r.get("summary")}, None, None)


def _ex_wiki(r: dict) -> tuple:
    prof = r.get("profile")
    return (bool(r.get("found")), [prof] if prof else [], {"summary": r.get("summary")}, None, None)


def _ex_geo(r: dict) -> tuple:
    match = r.get("match")
    items = ([match] if match else []) + (r.get("alternatives") or [])
    return (bool(match), items, {"summary": r.get("summary")}, None, None)


def _ex_tender(r: dict) -> tuple:
    return (True, r.get("tenders") or [],
            {"sources": r.get("sources"), "summary": r.get("summary"),
             "portal_leads": r.get("portal_leads")}, None, None)


# name -> (group, async call(keyword, limit)->raw, extractor, date_key, timeout_s).
# Timeout is PER SOURCE — slow sources (gdelt) get headroom without holding up the fast ones,
# because the frontend streams each panel in as it finishes (GET /scout/one).
def _social_call(platform: str) -> Callable:
    return lambda kw, lim: SOCIAL[platform](kw, limit=lim)


SPECS: dict[str, tuple] = {p: ("social", _social_call(p), _ex_social, "posted_at", 25.0) for p in SOCIAL}
SPECS.update({
    "news":      ("osint", lambda kw, lim: news_search(kw, limit=lim), _ex_news,   None,        15.0),
    "web":       ("osint", _web_call,                                _ex_web,      "published", 20.0),
    "company":   ("osint", lambda kw, lim: company_lookup(kw),       _ex_company,  None,        20.0),
    "academic":  ("osint", lambda kw, lim: academic_lookup(kw),      _ex_academic, "year",      20.0),
    "gdelt":     ("osint", lambda kw, lim: gdelt_coverage(kw),       _ex_gdelt,    "date",      50.0),
    "wikipedia": ("osint", lambda kw, lim: wiki_lookup(kw),          _ex_wiki,     None,        15.0),
    "geo":       ("osint", lambda kw, lim: geo_lookup(kw),           _ex_geo,      None,        15.0),
    "tenders":   ("osint", lambda kw, lim: tender_search(kw, limit=lim), _ex_tender, "published", 35.0),
})
ORDER: list[str] = list(SPECS.keys())   # social first, then osint


def source_list() -> list[dict]:
    return [{"name": n, "group": SPECS[n][0]} for n in ORDER]


async def run_one(name: str, keyword: str, limit: int = 8) -> dict:
    """Run ONE source (for streaming). Unknown name -> honest error envelope."""
    spec = SPECS.get(name)
    if not spec:
        return asdict(SourceResult(name, "?", False, 0, [], {}, None, "unknown source", 0.0))
    group, call, extract, date_key, timeout = spec
    r = await _guard(name, group, lambda: call(keyword, limit), extract, date_key, timeout)
    return asdict(r)


async def scout(keyword: str, limit: int = 8) -> list[dict]:
    """Full fan-out in one shot (kept for convenience; the UI uses run_one per source)."""
    results = await asyncio.gather(*(run_one(n, keyword, limit) for n in ORDER))
    return list(results)
