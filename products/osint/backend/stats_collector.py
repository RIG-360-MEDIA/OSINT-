"""Country macro-stats collector — a non-social OSINT source.

Given an ISO-2 country code, returns key World Bank development indicators
(GDP, population, GDP growth, inflation) with the latest available value per
indicator. Free, no API key, no auth. This is the Tasking-brain 'stats' source
made live for country/region keywords.
"""
from __future__ import annotations

from typing import Any

import httpx

_BASE = "https://api.worldbank.org/v2/country/{iso2}/indicator/{code}"
_PARAMS = {"format": "json", "date": "2020:2024", "per_page": "5"}

# indicator code -> short label used in the returned dict
_INDICATORS: dict[str, str] = {
    "NY.GDP.MKTP.CD": "gdp_usd",
    "SP.POP.TOTL": "population",
    "NY.GDP.MKTP.KD.ZG": "gdp_growth_pct",
    "FP.CPI.TOTL.ZG": "inflation_pct",
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


async def country_stats(country: str) -> dict[str, Any]:
    """Latest World Bank indicators for a country. Partial data on any failure."""
    iso2 = (country or "").strip().upper()
    if not _looks_like_iso2(iso2):
        return {"country": country, "error": "stats needs an ISO-2 country code, e.g. IN"}

    out: dict[str, Any] = {"country": iso2, "indicators": {}}
    country_name: str | None = None

    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        for code, label in _INDICATORS.items():
            url = _BASE.format(iso2=iso2, code=code)
            try:
                r = await client.get(url, params=_PARAMS)
                if r.status_code != 200:
                    out["indicators"][label] = {"error": f"http {r.status_code}"}
                    continue
                payload = r.json()
                # Shape is [meta, rows]; an unknown code yields a message dict.
                if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
                    out["indicators"][label] = {"error": "no data"}
                    continue
                rows = payload[1]
                country_name = country_name or rows[0].get("country", {}).get("value")
                latest = _latest_non_null(rows)
                out["indicators"][label] = latest or {"error": "no value in range"}
            except Exception as exc:  # never raise — graceful partial result
                out["indicators"][label] = {"error": type(exc).__name__}

    out["country_name"] = country_name
    gdp = out["indicators"].get("gdp_usd") or {}
    growth = out["indicators"].get("gdp_growth_pct") or {}
    gdp_val = gdp.get("value")
    growth_val = growth.get("value")
    out["summary"] = {
        "country_name": country_name,
        "gdp_usd": gdp_val,
        "gdp_usd_trillions": round(gdp_val / 1e12, 3) if isinstance(gdp_val, (int, float)) else None,
        "gdp_growth_pct": round(growth_val, 2) if isinstance(growth_val, (int, float)) else None,
        "gdp_year": gdp.get("year"),
        "headline": (
            f"{country_name or iso2}: GDP ${gdp_val / 1e12:.2f}T"
            f"{f', growth {growth_val:.1f}%' if isinstance(growth_val, (int, float)) else ''}"
            if isinstance(gdp_val, (int, float)) else None
        ),
    }
    return out
