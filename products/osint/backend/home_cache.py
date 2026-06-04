"""Per-persona Home payload cache + 30-min background refresher.

`build_home` is too heavy (~12-30s on the live window) to run per request, so we
serve a precomputed snapshot and refresh it on a 30-min cadence (aligned with the
matview refresh). The user never waits for the compute; a background task absorbs it.

  * get_home(...)      — serve cache if fresh (<FRESH_MIN); else compute live, store,
                         serve; on compute failure fall back to stale cache.
  * precompute_all()   — recompute + store every onboarded persona, EACH on its own
                         connection so one slow/failed persona can't poison the rest.
  * start_scheduler()  — fire-and-forget asyncio loop: warm on boot, then every REFRESH_MIN.

Table: analytics.home_cache(user_id pk, payload jsonb, computed_at timestamptz).
Writes commit explicitly — get_db() does not auto-commit. analytics_user has RW on analytics.*.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import text

from brief_prefs import load_prefs
from db import get_db
from home_sections import build_home
from war_room import build_war_room
from analytics_page import build_analytics

logger = logging.getLogger("osint-backend.home_cache")

FRESH_MIN = 35           # serve a cached payload up to this old (matview refreshes ~30m)
REFRESH_MIN = 30         # background recompute cadence
_BOOT_DELAY_S = 20       # let the app finish booting before the first warm
_COMPUTE_TIMEOUT_BG = "180s"   # generous ceiling for the background job
_COMPUTE_TIMEOUT_REQ = "60s"   # cold-miss lazy fill on the request path


async def _store(db, uid: str, payload: dict[str, Any]) -> None:
    await db.execute(text("""
        INSERT INTO analytics.home_cache (user_id, payload, computed_at)
        VALUES (CAST(:u AS uuid), CAST(:p AS jsonb), now())
        ON CONFLICT (user_id)
        DO UPDATE SET payload = EXCLUDED.payload, computed_at = now()
    """), {"u": uid, "p": json.dumps(payload, default=str)})
    await db.commit()


async def _read_row(db, uid: str):
    return (await db.execute(text("""
        SELECT payload, EXTRACT(EPOCH FROM (now() - computed_at)) / 60.0 AS age_min
          FROM analytics.home_cache WHERE user_id = CAST(:u AS uuid)
    """), {"u": uid})).fetchone()


async def get_home(db, uid: str, prefs: dict[str, Any], display_name: str | None,
                   *, max_age_min: float = FRESH_MIN) -> dict[str, Any]:
    """Cached payload if fresh; else compute live + store; else serve stale."""
    row = await _read_row(db, uid)
    if row and row.age_min is not None and row.age_min <= max_age_min:
        payload = dict(row.payload)
        payload["cache"] = {"hit": True, "age_min": round(float(row.age_min), 1)}
        return payload

    try:
        await db.execute(text(f"SET statement_timeout = '{_COMPUTE_TIMEOUT_REQ}'"))
        payload = await build_home(db, prefs, display_name=display_name)
        await _store(db, uid, payload)
        payload["cache"] = {"hit": False, "age_min": 0.0}
        return payload
    except Exception as exc:  # noqa: BLE001 — never 500 if we can serve something
        logger.warning("home_cache: live compute failed for %s (%s)", uid, exc)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        if row and row.payload is not None:  # serve stale rather than error
            payload = dict(row.payload)
            payload["cache"] = {"hit": True, "stale": True,
                                "age_min": round(float(row.age_min), 1) if row.age_min else None}
            return payload
        raise


# Generic page cache (analytics.page_cache) for the heavy pages.
async def _store_page(db, uid: str, page: str, payload: dict[str, Any]) -> None:
    await db.execute(text("""
        INSERT INTO analytics.page_cache (user_id, page, payload, computed_at)
        VALUES (CAST(:u AS uuid), :pg, CAST(:p AS jsonb), now())
        ON CONFLICT (user_id, page)
        DO UPDATE SET payload = EXCLUDED.payload, computed_at = now()
    """), {"u": uid, "pg": page, "p": json.dumps(payload, default=str)})
    await db.commit()


async def get_page(db, uid: str, page: str, builder, *, max_age_min: float = FRESH_MIN) -> dict[str, Any]:
    """Serve a cached page payload if fresh; else compute via builder(db) + store; else stale."""
    row = (await db.execute(text("""
        SELECT payload, EXTRACT(EPOCH FROM (now() - computed_at)) / 60.0 AS age_min
          FROM analytics.page_cache WHERE user_id = CAST(:u AS uuid) AND page = :pg
    """), {"u": uid, "pg": page})).fetchone()
    if row and row.age_min is not None and row.age_min <= max_age_min:
        payload = dict(row.payload)
        payload["cache"] = {"hit": True, "age_min": round(float(row.age_min), 1)}
        return payload
    try:
        await db.execute(text(f"SET statement_timeout = '{_COMPUTE_TIMEOUT_REQ}'"))
        payload = await builder(db)
        await _store_page(db, uid, page, payload)
        payload["cache"] = {"hit": False, "age_min": 0.0}
        return payload
    except Exception as exc:  # noqa: BLE001
        logger.warning("page_cache: live compute failed for %s/%s (%s)", uid, page, exc)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        if row and row.payload is not None:
            payload = dict(row.payload)
            payload["cache"] = {"hit": True, "stale": True}
            return payload
        raise


# Per-persona builders for the precompute batch: (page-key, callable(db, prefs, full_name)).
_PAGES = (
    ("home", lambda db, prefs, dn: build_home(db, prefs, display_name=dn)),
    ("warroom", lambda db, prefs, dn: build_war_room(db, prefs)),
    ("analytics", lambda db, prefs, dn: build_analytics(db, prefs)),
)


async def precompute_all() -> int:
    """Recompute + store every page for every onboarded persona. Each (persona, page)
    runs on its OWN connection so a slow/failed page can't poison the rest."""
    async with get_db() as db:
        rows = (await db.execute(text(
            "SELECT id::text AS id, full_name FROM analytics.users WHERE onboarded_at IS NOT NULL"
        ))).fetchall()

    done = 0
    for r in rows:
        any_ok = False
        for page, builder in _PAGES:
            try:
                async with get_db() as db:
                    await db.execute(text(f"SET statement_timeout = '{_COMPUTE_TIMEOUT_BG}'"))
                    prefs = await load_prefs(db, r.id)
                    if not prefs:
                        break
                    payload = await builder(db, prefs, r.full_name)
                    if page == "home":
                        await _store(db, r.id, payload)
                    else:
                        await _store_page(db, r.id, page, payload)
                any_ok = True
            except Exception as exc:  # noqa: BLE001 — one bad page/persona must not kill the batch
                logger.warning("cache: precompute %s failed for %s (%s)", page, r.id, exc)
        done += int(any_ok)
    logger.info("cache: precomputed %d/%d personas (pages: home, warroom, analytics)", done, len(rows))
    return done


async def _loop() -> None:
    await asyncio.sleep(_BOOT_DELAY_S)
    while True:
        try:
            await precompute_all()
        except Exception as exc:  # noqa: BLE001 — keep the loop alive across failures
            logger.warning("home_cache: precompute loop error (%s)", exc)
        await asyncio.sleep(REFRESH_MIN * 60)


def start_scheduler() -> asyncio.Task:
    """Fire-and-forget background refresher. osint-backend runs a single uvicorn
    worker, so there is exactly one scheduler."""
    logger.info("home_cache: starting %d-min precompute scheduler", REFRESH_MIN)
    return asyncio.create_task(_loop())
