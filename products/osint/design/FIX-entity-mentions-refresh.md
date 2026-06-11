# FIX — schedule the `article_entity_mentions` matview refresh

## Problem (verified 2026-06-02)
`article_entity_mentions` is a **materialized view** (the entity→article index every
personalization query joins on). It has a unique index (`article_entity_mentions_pk` on
`article_id, entity_id`) so it *can* refresh `CONCURRENTLY`, but **nothing in the codebase
refreshes it** — `grep -r 'article_entity_mentions' backend --include=*.py | grep -i refresh`
returns nothing. Its only refresh was a one-off on **2026-05-30 01:32 UTC**, so it froze:
source data ran to 1 Jun, the index stopped at 30 May, and it was **84% short** of current
(348,575 rows vs 639,677 after a manual refresh). The freshest 1–2 days were invisible to
personalization even though those were the two biggest ingest days in the corpus.

**Manual one-off already run** (`REFRESH MATERIALIZED VIEW CONCURRENTLY article_entity_mentions`,
8.3s, no read-lock) → index now current to 1 Jun. This doc is the **permanent** fix.

> Related: the CM page's `mv_cm_*` views (`refresh_views_task.py`) are **also not in the
> deployed `beat_schedule`** — they're likely going stale too. Worth fixing in the same pass.

---

## Patch 1 — new task file
`backend/tasks/refresh_entity_mentions_mv_task.py`
```python
"""
Refresh the article_entity_mentions materialized view — the entity→article index
that powers all personalization (watchlist → coverage). It had NO scheduled refresh
and went stale (frozen 2026-05-30). Unique index article_entity_mentions_pk allows a
CONCURRENTLY refresh (~8s, no read-lock).
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db

logger = logging.getLogger(__name__)


async def _refresh() -> None:
    async with get_db() as db:
        try:
            await db.execute(
                text("REFRESH MATERIALIZED VIEW CONCURRENTLY article_entity_mentions")
            )
            await db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("CONCURRENTLY refresh failed (%s) — falling back to plain", exc)
            await db.execute(text("REFRESH MATERIALIZED VIEW article_entity_mentions"))
            await db.commit()


@app.task(name="tasks.refresh_entity_mentions_mv")
def refresh_entity_mentions_mv() -> dict[str, str]:
    asyncio.run(_refresh())
    return {"refreshed": "article_entity_mentions"}
```

## Patch 2 — `backend/celery_app.py` (three inserts)

**(a) `include=[...]`** — after the `entity_mention_task` line:
```diff
         # Hourly entity-mention aggregator (T6)
         "backend.tasks.entity_mention_task",
+        # 30-min refresh of the article_entity_mentions matview (personalization
+        # index) — had NO scheduled refresh and went stale. See FIX doc 2026-06.
+        "backend.tasks.refresh_entity_mentions_mv_task",
```

**(b) `task_routes` dict** — after the `entity_mentions` route:
```diff
             "tasks.quality.entity_mentions": {"queue": "nlp"},
+            "tasks.refresh_entity_mentions_mv": {"queue": "nlp"},
```

**(c) `beat_schedule` dict** — after the `entity-mentions-every-60-min` entry:
```diff
             "entity-mentions-every-60-min": {
                 "task": "tasks.quality.entity_mentions",
                 "schedule": timedelta(minutes=60),
                 "options": {"queue": "nlp"},
             },
+            # Refresh the article_entity_mentions matview (personalization index)
+            # every 30 min — CONCURRENTLY, ~8s, no read-lock. Fixes the stale-index
+            # bug where the newest days were invisible to personalization.
+            "refresh-entity-mentions-mv-every-30-min": {
+                "task": "tasks.refresh_entity_mentions_mv",
+                "schedule": timedelta(minutes=30),
+                "options": {"queue": "nlp"},
+            },
```

## Deploy
The refresh runs on the **`nlp`** queue (worker-nlp, concurrency 4). After applying:
```bash
# rebuild if backend code is baked into the image, else just restart
docker compose -f infrastructure/docker-compose.yml build rig-backend
docker restart rig-backend
# verify the beat entry registered:
docker exec rig-backend celery -A backend.celery_app inspect scheduled | grep entity_mentions_mv
```

---

## Alternative — host cron (zero code, branch-agnostic, immediate)
Because the local repo is diverged (`feat/clustering-story-layer-0a` lacks this wiring),
the Celery change can't deploy until branch reconciliation. A host cron is an immediate,
robust guard that needs no code or branch work:
```cron
# /etc/cron.d/aem-refresh  — refresh personalization index every 30 min
*/30 * * * * root docker exec rig-postgres psql -U rig -d rig -c "REFRESH MATERIALIZED VIEW CONCURRENTLY article_entity_mentions" >> /var/log/aem_refresh.log 2>&1
```
Recommended **now** (cron), then fold Patch 1–2 in during the next branch reconciliation so
the refresh lives with the rest of the schedule.

---

## STATUS — deployed 2026-06-02
- **One-off refresh:** done (`article_entity_mentions` 348,575 → 639,677 rows, current to 1 Jun).
- **Cron:** **DEPLOYED** → `/etc/cron.d/rig-matview-refresh` (root:root 644, LF, BOM-stripped),
  every 30 min, CONCURRENTLY, covers `article_entity_mentions` + `mv_cm_voice_share` +
  `mv_cm_issue_hourly` + `mv_cm_constituency_daily`. Test-run passed; cron daemon active.
  Log: `/var/log/rig_matview_refresh.log`.
- **CM views (were 0 rows / never refreshed):** populated — `mv_cm_voice_share` 2,116,
  `mv_cm_constituency_daily` 29. `mv_cm_issue_hourly` refreshes clean but yields 0 rows
  (upstream issue/stance data empty — separate fix).
- **Celery Patch 1–2: NOT applied.** `rig-backend` code is **baked into the image** (only the
  beat-schedule volume + youtube cookies are bind-mounted), so editing files + `docker restart`
  would not load new code — it needs a full `docker compose build`. The cron supersedes it for
  now; apply Patch 1–2 at the next rebuild/branch reconciliation, then drop the cron lines.
## Related matviews — diagnosed & partially fixed 2026-06-02
Same "no scheduled refresh" disease, but two of these are **upstream-data** gaps, not refresh gaps:

**`mv_cm_issue_hourly`** — refreshes clean but **0 rows**. Source `cm_issue_evidence` has
5,810 rows but its **latest linked article is 2026-05-25**; the view's `published_at > now()-7d`
filter excludes all of it. → **The CM issue-evidence builder stalled ~25 May.** The matview is
in the cron and will auto-fill once that task resumes. *Fix = restart the evidence-builder task
(backend; baked-image/branch constraint applies — same as Patch 1–2).*

**District views (`mv_district_*`)** — refresh works; the question is the source:
- **Article-derived (WORK, now in cron):** `mv_district_news_volume_24h` (59),
  `mv_district_sentiment_24h` (59), `mv_district_stability_composite` (59). Added to the cron
  (sliding 24h windows — need frequent refresh; all have unique indexes → CONCURRENTLY).
- **External-collector (EMPTY — source has 0 rows):** `acled_7d`←`acled_events` (0),
  `power_stress`←`power_grid_status` (0), `mandi_volatility_30d`←`mandi_prices` (0),
  `welfare_coverage`←`welfare_coverage` (0). The atlas collectors (ACLED / agmarknet /
  tgspdcl / welfare) **have produced no data**. Left out of the cron (pointless on empty
  source). *Fix = the worldmonitor collector subsystem — separate investigation.*

### Cron now covers 7 matviews
`article_entity_mentions` · `mv_cm_voice_share` · `mv_cm_issue_hourly` ·
`mv_cm_constituency_daily` · `mv_district_news_volume_24h` · `mv_district_sentiment_24h` ·
`mv_district_stability_composite` — all CONCURRENTLY, composite after its components, every 30 min.
