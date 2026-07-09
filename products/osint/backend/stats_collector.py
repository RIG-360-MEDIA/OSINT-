"""Country macro-stats collector — a non-social OSINT source.

Given an ISO-2 country code, returns key World Bank indicators (GDP, population,
GDP growth, inflation, MILITARY EXPENDITURE, exports) with the latest available
value per indicator. Free, no API key, no auth. Military spend + trade make it
useful for defence/market clients. This is the Tasking-brain 'stats' source made
live for country/region keywords (routed an ISO-2 by geo classification).
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

_BASE = "https://api.worldbank.org/v2/country/{iso2}/indicator/{code}"
_PARAMS = {"format": "json", "date": "2018:2024", "per_page": "8"}

# indicator code -> short label used in the returned dict
_INDICATORS: dict[str, str] = {
    "NY.GDP.MKTP.CD": "gdp_usd",
    "SP.POP.TOTL": "population",
    "NY.GDP.MKTP.KD.ZG": "gdp_growth_pct",
    "FP.CPI.TOTL.ZG": "inflation_pct",
    "MS.MIL.XPND.CD": "military_exp_usd",
    "MS.MIL.XPND.GD.ZS": "military_exp_pct_gdp",
    "NE.EXP.GNFS.CD": "exports_usd",
}


def _looks_like_iso2(s: str) -> bool:
    s = (s or "").strip()
    return len(s) == 2 and s.isalpha()


def _latest_non_null(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """World Bank returns rows newest-first; take the first with a value."""
    for row in rows or []:
        if row.get("value") is not None:
            return {"value": row["value"], "year": row.get("date")}
    return None


async def _fetch(client: httpx.AsyncClient, iso2: str, code: str,
                 label: str) -> tuple[str, dict[str, Any], str | None]:
    """One indicator; returns (label, value-dict, country_name-if-seen)."""
    try:
        r = await client.get(_BASE.format(iso2=iso2, code=code), params=_PARAMS)
        if r.status_code != 200:
            return label, {"error": f"http {r.status_code}"}, None
        payload = r.json()
        if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
            return label, {"error": "no data"}, None
        rows = payload[1]
        name = (rows[0].get("country", {}) or {}).get("value")
        return label, (_latest_non_null(rows) or {"error": "no value in range"}), name
    except Exception as exc:
        return label, {"error": type(exc).__name__}, None


async def country_stats(country: str) -> dict[str, Any]:
    """Latest World Bank indicators for a country. Partial data on any failure."""
    iso2 = (country or "").strip().upper()
    if not _looks_like_iso2(iso2):
        return {"country": country, "error": "stats needs an ISO-2 country code, e.g. IN"}

    out: dict[str, Any] = {"country": iso2, "indicators": {}}
    country_name: str | None = None
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        results = await asyncio.gather(
            *[_fetch(client, iso2, code, label) for code, label in _INDICATORS.items()])
    for label, value, name in results:
        out["indicators"][label] = value
        country_name = country_name or name

    out["country_name"] = country_name

    def _val(label: str) -> Any:
        v = (out["indicators"].get(label) or {}).get("value")
        return v if isinstance(v, (int, float)) else None

    gdp = _val("gdp_usd")
    growth = _val("gdp_growth_pct")
    mil = _val("military_exp_usd")
    out["summary"] = {
        "country_name": country_name,
        "gdp_usd_trillions": round(gdp / 1e12, 3) if gdp else None,
        "gdp_growth_pct": round(growth, 2) if growth is not None else None,
        "population": _val("population"),
        "inflation_pct": round(_val("inflation_pct"), 2) if _val("inflation_pct") is not None else None,
        "military_exp_usd_bn": round(mil / 1e9, 2) if mil else None,
        "military_exp_pct_gdp": _val("military_exp_pct_gdp"),
        "exports_usd_bn": round(_val("exports_usd") / 1e9, 1) if _val("exports_usd") else None,
        "gdp_year": (out["indicators"].get("gdp_usd") or {}).get("year"),
        "headline": (
            f"{country_name or iso2}: GDP ${gdp / 1e12:.2f}T"
            f"{f', growth {growth:.1f}%' if growth is not None else ''}"
            f"{f', defence ${mil / 1e9:.0f}B' if mil else ''}"
            if gdp else None
        ),
    }
    return out
