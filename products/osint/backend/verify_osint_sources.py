"""OSINT-sources verifier — proves every free source live, on a real input.

    python verify_osint_sources.py "<keyword>" [--domain d] [--country XX]

For each source prints: API host · ok/fail · 2-3 REAL result fields · elapsed.
Routes the one input to each source's needed shape: keyword direct; domain
derived from SearXNG (or --domain); country from geo (or --country). Honest —
an empty/failed source is reported as such, never silently skipped.

Run on dev AND the Hetzner osint-backend, on >=2 inputs (one common, one fresh).
"""
from __future__ import annotations

import asyncio
import sys
import time
from typing import Any, Awaitable, Callable

from academic_collector import academic_lookup
from archive_collector import web_archive
from company_collector import company_lookup
from gdelt_collector import gdelt_coverage
from geo_collector import geo_lookup
from infra_collector import domain_infra
from searxng_collector import web_search
from stats_collector import country_stats
from tender_collector import tender_search
from wiki_collector import wiki_lookup


async def _timed(name: str, api: str, coro: Awaitable[dict[str, Any]],
                 fields: Callable[[dict[str, Any]], dict[str, Any]],
                 ok: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
    t0 = time.monotonic()
    try:
        r = await coro
        return {"source": name, "api": api, "ok": ok(r),
                "fields": fields(r), "elapsed_s": round(time.monotonic() - t0, 1),
                "error": r.get("error")}
    except Exception as exc:
        return {"source": name, "api": api, "ok": False, "fields": {},
                "elapsed_s": round(time.monotonic() - t0, 1),
                "error": f"{type(exc).__name__}: {exc}"}


async def verify(keyword: str, domain: str | None = None,
                 country: str | None = None) -> list[dict[str, Any]]:
    # Route the single input to each source's shape.
    ws = await web_search(keyword, limit=5)
    domain = domain or (ws.get("summary") or {}).get("official_domain")
    if not country:
        geo = await geo_lookup(keyword)
        country = ((geo.get("match") or {}).get("country_code")) or "IN"

    def s(r):  # searxng
        sm = r.get("summary") or {}
        return {"results": sm.get("result_count"), "official_domain": sm.get("official_domain"),
                "sources": sm.get("distinct_sources")}

    checks = [
        _timed("SearXNG web", "rig-searxng:8080", _echo(ws), s, lambda r: bool((r.get("summary") or {}).get("result_count"))),
        _timed("Company", "api.gleif.org", company_lookup(keyword),
               lambda r: {"resolved": (r.get("summary") or {}).get("legal_name"),
                          "reg_id": (r.get("summary") or {}).get("registration_id"),
                          "subsidiaries": (r.get("summary") or {}).get("subsidiaries")},
               lambda r: bool((r.get("summary") or {}).get("resolved"))),
        _timed("Wiki", "en.wikipedia.org", wiki_lookup(keyword),
               lambda r: {"one_line": (r.get("summary") or {}).get("one_line"),
                          "qid": (r.get("summary") or {}).get("wikidata_qid")},
               lambda r: bool((r.get("summary") or {}).get("found"))),
        _timed("Academic", "api.openalex.org", academic_lookup(keyword),
               lambda r: {"total_works": (r.get("summary") or {}).get("total_works"),
                          "fields": (r.get("summary") or {}).get("top_fields"),
                          "top_author": ((r.get("summary") or {}).get("top_authors") or [None])[0]},
               lambda r: (r.get("summary") or {}).get("total_works") is not None),
        _timed("Geo", "nominatim.osm.org", geo_lookup(keyword),
               lambda r: {"coords": (r.get("summary") or {}).get("coordinates"),
                          "type": (r.get("summary") or {}).get("place_type"),
                          "country": (r.get("summary") or {}).get("country")},
               lambda r: bool((r.get("summary") or {}).get("found"))),
        _timed("GDELT news", "api.gdeltproject.org", gdelt_coverage(keyword),
               lambda r: {"articles": (r.get("summary") or {}).get("article_count"),
                          "countries": (r.get("summary") or {}).get("top_countries")},
               lambda r: bool((r.get("summary") or {}).get("article_count"))),
        _timed("Tenders", "TED + WorldBank + TenderNews", tender_search(keyword, region="all", limit=6),
               lambda r: {"total": (r.get("summary") or {}).get("total_returned"),
                          "sources_ok": (r.get("summary") or {}).get("sources_ok")},
               lambda r: bool((r.get("summary") or {}).get("total_returned"))),
    ]
    # Domain-scoped sources (need a domain).
    if domain:
        checks += [
            _timed(f"Infra [{domain}]", "rdap.org + dns.google + crt.sh", domain_infra(domain),
                   lambda r: {"hosting": (r.get("summary") or {}).get("hosting_provider"),
                              "subdomains": (r.get("summary") or {}).get("subdomain_count"),
                              "created": (r.get("summary") or {}).get("domain_created")},
                   lambda r: bool(r.get("dns", {}).get("A") or r.get("rdap"))),
            _timed(f"Archive [{domain}]", "web.archive.org", web_archive(domain),
                   lambda r: {"first": (r.get("summary") or {}).get("first_seen_year"),
                              "snapshots": (r.get("summary") or {}).get("total_snapshots")},
                   lambda r: bool((r.get("summary") or {}).get("archived"))),
        ]
    # Country-scoped source.
    checks.append(
        _timed(f"Stats [{country}]", "api.worldbank.org", country_stats(country),
               lambda r: {"gdp_T": (r.get("summary") or {}).get("gdp_usd_trillions"),
                          "defence_bn": (r.get("summary") or {}).get("military_exp_usd_bn")},
               lambda r: bool((r.get("summary") or {}).get("gdp_usd_trillions"))))

    return await asyncio.gather(*checks)


async def _echo(v: dict[str, Any]) -> dict[str, Any]:
    return v


def _main() -> None:
    args = [a for a in sys.argv[1:]]
    keyword, domain, country = None, None, None
    i = 0
    while i < len(args):
        if args[i] == "--domain" and i + 1 < len(args):
            domain = args[i + 1]; i += 2
        elif args[i] == "--country" and i + 1 < len(args):
            country = args[i + 1]; i += 2
        else:
            keyword = args[i]; i += 1
    if not keyword:
        print('usage: verify_osint_sources.py "<keyword>" [--domain d] [--country XX]')
        return

    rows = asyncio.run(verify(keyword, domain, country))
    print(f'\n=== OSINT sources · input="{keyword}" ===')
    print(f'{"SOURCE":<20}{"OK":<4}{"API":<34}{"s":<6}FIELDS')
    for r in sorted(rows, key=lambda x: x["source"]):
        flag = "OK" if r["ok"] else "--"
        fields = ", ".join(f"{k}={v}" for k, v in (r["fields"] or {}).items() if v not in (None, []))
        note = f"  ERR:{r['error']}" if r.get("error") and not r["ok"] else ""
        print(f'{r["source"]:<20}{flag:<4}{r["api"]:<34}{r["elapsed_s"]:<6}{fields[:90]}{note}')
    n_ok = sum(1 for r in rows if r["ok"])
    print(f'\n{n_ok}/{len(rows)} sources returned real data.')


if __name__ == "__main__":
    _main()
