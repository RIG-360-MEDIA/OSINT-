"""GDELT global-coverage collector — worldwide news volume + tone for a keyword.

Uses the free GDELT DOC 2.0 API (no key, no auth). Two calls:
  - mode=timelinevol   → coverage volume over ~7d (percent of all global coverage)
  - mode=timelinetone  → average tone over ~7d (GDELT tone scale, ~ -10..+10)

For any keyword this gives WORLDWIDE news attention + sentiment, beyond the India
corpus. GDELT throttles to one request / 5s and answers over-rate with a plain-text
notice (not JSON), so calls are spaced and every response is validated before parsing.
"""
from __future__ import annotations

import asyncio
from statistics import mean
from typing import Any

import httpx

_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
_HEADERS = {"User-Agent": "RIG-OSINT/1.0"}
_TIMESPAN = "7d"
_RATE_GAP = 5.5  # GDELT asks for >=5s between requests


async def _timeline(client: httpx.AsyncClient, query: str, mode: str) -> list[dict[str, Any]]:
    """Fetch one GDELT timeline series. Raises on non-JSON (throttle) so caller records it."""
    params = {"query": query, "mode": mode, "format": "json", "timespan": _TIMESPAN}
    r = await client.get(_BASE, params=params, headers=_HEADERS)
    body = r.text.strip()
    if r.status_code != 200 or not body.startswith("{"):
        raise ValueError(f"gdelt {mode} non-json (status {r.status_code})")
    timeline = r.json().get("timeline") or []
    return timeline[0].get("data") or [] if timeline else []


def _values(points: list[dict[str, Any]]) -> list[float]:
    out: list[float] = []
    for p in points:
        try:
            out.append(float(p.get("value")))
        except (TypeError, ValueError):
            continue
    return out


async def gdelt_coverage(q: str) -> dict[str, Any]:
    """Worldwide 7-day news volume + tone for a keyword. Partial data on any failure."""
    q = (q or "").strip()
    if not q:
        return {"query": q, "error": "empty query"}

    out: dict[str, Any] = {"query": q, "timespan": _TIMESPAN, "volume": None, "tone": None}
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        try:
            vol = await _timeline(client, q, "timelinevol")
            vals = _values(vol)
            out["volume"] = {
                "points": len(vals),
                "total_intensity": round(sum(vals), 4),
                "peak_intensity": round(max(vals), 4) if vals else 0.0,
                "latest_intensity": round(vals[-1], 4) if vals else 0.0,
            }
        except Exception as exc:
            out["volume_error"] = type(exc).__name__

        await asyncio.sleep(_RATE_GAP)  # respect GDELT's one-request-per-5s limit

        try:
            tone = await _timeline(client, q, "timelinetone")
            vals = _values(tone)
            avg = round(mean(vals), 3) if vals else None
            out["tone"] = {
                "points": len(vals),
                "avg_tone": avg,
                "min_tone": round(min(vals), 3) if vals else None,
                "max_tone": round(max(vals), 3) if vals else None,
            }
        except Exception as exc:
            out["tone_error"] = type(exc).__name__

    avg_tone = (out.get("tone") or {}).get("avg_tone")
    out["summary"] = {
        "has_global_coverage": bool((out.get("volume") or {}).get("total_intensity")),
        "total_intensity": (out.get("volume") or {}).get("total_intensity"),
        "avg_tone": avg_tone,
        "sentiment": (
            None if avg_tone is None
            else "positive" if avg_tone > 1
            else "negative" if avg_tone < -1
            else "neutral"
        ),
    }
    return out
