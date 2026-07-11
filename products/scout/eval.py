"""Scout eval scorecard — objective metrics, NO fabricated labels.

Runs a gold set of keywords through every source and reports, PER SOURCE:
  reliability  = % of keywords the source returned >=1 result for (catches dead sources)
  med_count    = median results returned
  relevance    = % of items whose text contains ALL query tokens — an honest keyword-presence
                 PROXY, NOT human precision@10 (labeled as such; a floor on topicality)
  med_age_days = median freshness of dated items (lower = fresher)

Run inside the rigscout container (all sources incl. SearXNG reachable):
    docker exec rigscout python /work/products/scout/eval.py
Writes eval_report.json next to this file and prints a table.
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
from datetime import datetime, timezone

import httpx

BASE = os.environ.get("SCOUT_BASE", "http://127.0.0.1:8610")
GOLD = [
    "PLA navy", "Rafale", "Adani", "missile", "Narendra Modi", "Windlass", "Taiwan",
    "semiconductor", "Reliance", "drone warfare", "Balochistan", "cyber attack",
    "INS Vikrant", "Xi Jinping", "climate summit", "AI regulation", "Ukraine",
    "Hamas", "quantum computing", "defence tender",
]
TEXT_FIELDS = ("title", "post_text", "text", "snippet", "description", "extract", "legal_name",
               "name", "display_name", "headline", "claim")
DATE_FIELDS = ("posted_at", "published", "date", "pubDate")
_DATE_FMTS = ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%a, %d %b %Y %H:%M:%S %z",
              "%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%d", "%Y")


def _age_days(item: dict) -> float | None:
    for f in DATE_FIELDS:
        v = item.get(f)
        if not v:
            continue
        s = str(v).strip().replace("Z", "+0000")
        for fmt in _DATE_FMTS:
            try:
                d = datetime.strptime(s[:31], fmt)
                if d.tzinfo is None:
                    d = d.replace(tzinfo=timezone.utc)
                return max(0.0, (datetime.now(timezone.utc) - d).total_seconds() / 86400)
            except ValueError:
                continue
    return None


def _relevant(item: dict, tokens: list[str]) -> bool:
    blob = " ".join(str(item.get(f, "")) for f in TEXT_FIELDS).lower()
    return all(t in blob for t in tokens)


_SEM = asyncio.Semaphore(12)


async def _sources(client: httpx.AsyncClient) -> list[str]:
    r = await client.get(f"{BASE}/scout/sources", timeout=15)
    # identity is gated/slow (maigret) and not a keyword-content source — skip it in the eval.
    return [s["name"] for s in r.json().get("sources", []) if s["name"] != "identity"]


async def _one(client: httpx.AsyncClient, kw: str, name: str) -> dict:
    async with _SEM:
        try:
            r = await client.get(f"{BASE}/scout/one", params={"name": name, "keyword": kw, "limit": 10}, timeout=70)
            return r.json()
        except Exception as exc:
            return {"name": name, "group": "?", "count": 0, "items": [], "error": type(exc).__name__}


async def main() -> None:
    per_source: dict[str, dict] = {}
    async with httpx.AsyncClient() as client:
        names = await _sources(client)
        pairs = [(kw, n) for kw in GOLD for n in names]
        print(f"running {len(pairs)} (keyword×source) probes concurrently…", flush=True)
        results = await asyncio.gather(*[_one(client, kw, n) for kw, n in pairs])
        for (kw, _n), s in zip(pairs, results):
            tokens = [t for t in kw.lower().split() if t]
            acc = per_source.setdefault(s.get("name", _n), {"group": s.get("group", "?"), "returned": 0,
                                                           "counts": [], "rel": [], "ages": []})
            items = s.get("items") or []
            if s.get("count"):
                acc["returned"] += 1
                acc["counts"].append(s["count"])
                acc["rel"].append(sum(_relevant(it, tokens) for it in items) / len(items) if items else 0)
                acc["ages"] += [a for a in (_age_days(it) for it in items) if a is not None]
        print("all probes done", flush=True)

    n = len(GOLD)
    rows = []
    for name, a in per_source.items():
        rows.append({
            "source": name, "group": a["group"],
            "reliability_pct": round(100 * a["returned"] / n, 1),
            "med_count": round(statistics.median(a["counts"]), 1) if a["counts"] else 0,
            "relevance_proxy_pct": round(100 * statistics.mean(a["rel"]), 1) if a["rel"] else 0,
            "med_age_days": round(statistics.median(a["ages"]), 1) if a["ages"] else None,
        })
    rows.sort(key=lambda r: (-r["reliability_pct"], -r["relevance_proxy_pct"]))

    report = {"keywords": GOLD, "n": n, "rows": rows,
              "note": "relevance_proxy = keyword-presence floor, NOT human precision@10"}
    out = os.path.join(os.path.dirname(__file__), "eval_report.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    print(f"\n=== SCOUT SCORECARD ({n} gold keywords) ===")
    print(f"{'source':<12}{'grp':<9}{'reliab%':>8}{'medCnt':>8}{'relev%':>8}{'ageDays':>9}")
    for r in rows:
        print(f"{r['source']:<12}{r['group']:<9}{r['reliability_pct']:>8}{r['med_count']:>8}"
              f"{r['relevance_proxy_pct']:>8}{str(r['med_age_days']):>9}")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
