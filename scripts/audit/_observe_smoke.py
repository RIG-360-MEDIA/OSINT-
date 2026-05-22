"""Live smoke test for the /observe helpers — runs inside rig-backend.

Usage:
    docker exec rig-backend python /app/scripts/audit/_observe_smoke.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")

from backend.database import get_db  # noqa: E402
from backend.observability.article_quality import (  # noqa: E402
    crosstab,
    geo_heatmap,
    ingest_pulse,
    live_tail,
    quality_monitor,
    source_scorecard,
    story_pulse,
)
from backend.observability.audit_queue import audit_queue  # noqa: E402


async def main() -> int:
    async with get_db() as db:
        ip = await ingest_pulse(db)
        print(f"ingest_pulse OK: total_24h={ip['total_24h']} sources={len(ip['per_source'])} stalled={len(ip['stalled_sources'])}")

        sc = await source_scorecard(db)
        print(f"source_scorecard OK: sources={len(sc['sources'])}")

        qm = await quality_monitor(db)
        live = qm["live"]
        print(f"quality_monitor OK: claims_placeholder_pct={live['claims_placeholder_pct']} cliff_500={live['cliff_500']}")

        for lvl in ("country", "state", "district"):
            gh = await geo_heatmap(db, level=lvl)
            print(f"geo_heatmap {lvl} OK: regions={len(gh['regions'])}")

        sp = await story_pulse(db, limit=5)
        print(f"story_pulse OK: clusters={len(sp['clusters'])}")

        ct = await crosstab(db, actor="Modi", time_window_days=60)
        print(f"crosstab Modi OK: rows={len(ct['rows'])}")

        lt = await live_tail(db, limit=5)
        print(f"live_tail OK: articles={len(lt['articles'])}")

        aq = await audit_queue(db, limit=5)
        print(f"audit_queue OK: queue={len(aq['queue'])}")
    print("ALL helpers responded.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
