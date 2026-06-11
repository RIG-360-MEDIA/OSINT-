"""Smoke test the new /observe v2 helpers (corpus, pipeline, trending)."""
import asyncio
import sys
sys.path.insert(0, "/app")
from backend.database import get_db
from backend.observability.overview_helpers import (
    corpus_overview, pipeline_health, trending_entities,
)


async def main():
    async with get_db() as db:
        print("=== corpus_overview ===")
        c = await corpus_overview(db)
        for k, v in c.items():
            print(f"  {k:20s} {v:>10,}" if isinstance(v, int) else f"  {k:20s} {v}")
        print()
        print("=== pipeline_health ===")
        ph = await pipeline_health(db)
        print("  T4:", ph["t4_backfill"])
        print("  V3:", ph["v3_upgrade"])
        if ph.get("latest_regression"):
            r = ph["latest_regression"]
            print(f"  Regression: passed={r['passed']} {r.get('matched')}/{r.get('gold_size')}")
        print()
        print("=== trending_entities (top 8) ===")
        t = await trending_entities(db, limit=8)
        for e in t["entities"]:
            tag = "NEW" if e["is_new"] else (f"SURGE {e['surge_ratio']}x" if e["is_surging"] else "")
            print(f"  {e['entity'][:30]:30s}  today={e['mentions_today']:>4}  sources={e['sources_today']:>3}  {tag}")


asyncio.run(main())
