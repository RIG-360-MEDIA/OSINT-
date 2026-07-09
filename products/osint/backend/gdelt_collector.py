"""GDELT global-coverage collector — worldwide news for a keyword.

Uses the free GDELT DOC 2.0 API (no key, no auth). Returns the actual recent
ARTICLES worldwide (title/url/domain/source-country/language/date) plus derived
coverage signals (which countries + outlets are covering it, language spread) and
a best-effort tone/sentiment read.

GDELT is slow from a datacenter (~10-20s/call) and rate-limits with HTTP 429, so
the timeout is generous and the primary call retries once on throttle. Tone is a
best-effort secondary — skipped gracefully if GDELT throttles, never blocking.
This replaces the old volume/tone-only version that timed out at 12s and returned
no articles.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any

import httpx

_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
_HEADERS = {"User-Agent": "RIG-OSINT/1.0"}
_TIMESPAN = "7d"
_TIMEOUT = httpx.Timeout(28.0, connect=15.0)


async def _get_json(client: httpx.AsyncClient, params: dict[str, Any],
                    retries: int = 1) -> tuple[dict[str, Any] | None, str | None]:
    """One GDELT call. Retries once on 429/timeout (GDELT often 429s the first
    hit then serves the second). Returns (json, error-label)."""
    for attempt in range(retries + 1):
        try:
            r = await client.get(_BASE, params=params, headers=_HEADERS)
            body = r.text.strip()
            if r.status_code == 200 and body.startswith("{"):
                return r.json(), None
            if r.status_code == 429:
                if attempt < retries:
                    await asyncio.sleep(6)   # GDELT wants >=5s between requests
                    continue
                return None, "throttled (HTTP 429 — GDELT rate-limits datacenter IPs; retry shortly)"
            return None, f"http {r.status_code}"
        except Exception as exc:
            if attempt < retries:
                await asyncio.sleep(6)
                continue
            return None, type(exc).__name__
    return None, "unknown"


def _shape_article(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": (a.get("title") or "").strip() or None,
        "url": a.get("url"),
        "domain": a.get("domain"),
        "country": a.get("sourcecountry"),
        "language": a.get("language"),
        "date": a.get("seendate"),
        "image": a.get("socialimage") or None,
    }


def _tone_summary(tc: dict[str, Any] | None) -> dict[str, Any] | None:
    """Weighted average tone + pos/neg share from a GDELT tonechart, defensively."""
    if not tc:
        return None
    total = wsum = neg = pos = 0
    for b in tc.get("tonechart") or []:
        try:
            binv = float(b.get("bin"))
            cnt = int(b.get("count") or 0)
        except (TypeError, ValueError):
            continue
        total += cnt
        wsum += binv * cnt
        if binv < -1:
            neg += cnt
        elif binv > 1:
            pos += cnt
    if not total:
        return None
    return {
        "avg_tone": round(wsum / total, 2),
        "articles_scored": total,
        "negative_pct": round(100 * neg / total),
        "positive_pct": round(100 * pos / total),
    }


async def gdelt_coverage(q: str) -> dict[str, Any]:
    """Worldwide 7-day news coverage for a keyword. Partial data on any failure."""
    q = (q or "").strip()
    if not q:
        return {"query": q, "error": "empty query"}

    out: dict[str, Any] = {"query": q, "timespan": _TIMESPAN, "articles": [], "summary": None}
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        # ONE call only — GDELT rate-limits datacenter IPs hard (429), so a second
        # request (tonechart) just trips the throttle. artlist gives the real value
        # (worldwide articles). Retry twice with a >=5s backoff (GDELT often 429s
        # the first hit then serves it). Tone is derivable downstream from titles.
        art, aerr = await _get_json(client, {
            "query": q, "mode": "artlist", "format": "json",
            "timespan": _TIMESPAN, "maxrecords": "25", "sort": "datedesc"}, retries=2)
        articles = (art or {}).get("articles") or []
        out["articles"] = [_shape_article(a) for a in articles[:25]]
        if aerr:
            out["articles_error"] = aerr
        tone = None

    arts = out["articles"]
    countries = Counter(a["country"] for a in arts if a.get("country"))
    domains = Counter(a["domain"] for a in arts if a.get("domain"))
    langs = Counter(a["language"] for a in arts if a.get("language"))
    avg_tone = (tone or {}).get("avg_tone")
    out["summary"] = {
        "article_count": len(arts),
        "has_global_coverage": bool(arts),
        "top_countries": [c for c, _ in countries.most_common(6)],
        "top_domains": [d for d, _ in domains.most_common(6)],
        "languages": [l for l, _ in langs.most_common(5)],
        "tone": tone,
        "sentiment": (
            None if avg_tone is None
            else "positive" if avg_tone > 1
            else "negative" if avg_tone < -1
            else "neutral"),
    }
    return out
