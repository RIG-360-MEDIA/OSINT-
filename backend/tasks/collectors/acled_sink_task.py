"""
ACLED events sink. Persists conflict / protest / riot events for
Telangana + Andhra Pradesh into ``acled_events`` so downstream MVs
(`mv_district_acled_7d`, stability composite) have a stable read.

Cadence: every 6 hours.

The live ``worldmonitor_router`` already calls the ACLED API for
real-time fetches; this task reuses the same HTTP path but stores
results so we can compute 7-day rolling counts and aggregate per
district. The ACLED API requires ACLED_ACCESS_TOKEN (free, register
at acleddata.com).

District resolution: lat/lon → nearest district centroid via
``district_for_lat_lon``. Falls back to ``district_for_name`` against
``location`` / ``admin2`` when coords are missing.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db
from backend.tasks.collectors._cm_helpers import (
    district_for_lat_lon,
    district_for_name,
    record_run_health,
)

logger = logging.getLogger(__name__)


SOURCE_ID = "acled_sink"
TIMEOUT_S = 30.0
ENDPOINT = "https://api.acleddata.com/acled/read"
LOOKBACK_DAYS = 14
PAGE_SIZE = 500
COUNTRY = "India"
ADMIN1_FILTERS = ("Telangana", "Andhra Pradesh")


def _safe_float(v: Any) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (ValueError, TypeError):
        return None


def _safe_int(v: Any) -> int | None:
    try:
        return int(v) if v not in (None, "") else None
    except (ValueError, TypeError):
        return None


def _safe_date(v: Any) -> date | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v)).date()
    except (ValueError, TypeError):
        try:
            return datetime.strptime(str(v), "%Y-%m-%d").date()
        except ValueError:
            return None


async def _fetch_admin1(client: httpx.AsyncClient, admin1: str, token: str, key: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    page = 1
    earliest = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).date().isoformat()
    while True:
        params = {
            "country": COUNTRY,
            "admin1": admin1,
            "event_date": f"{earliest}|{datetime.now(timezone.utc).date().isoformat()}",
            "event_date_where": "BETWEEN",
            "limit": PAGE_SIZE,
            "page": page,
            "terms": "accept",
            "access_token": token,
        }
        if key:
            params["key"] = key
        try:
            resp = await client.get(ENDPOINT, params=params)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("acled fetch failed (admin1=%s page=%d): %s", admin1, page, exc)
            break
        rows = payload.get("data") or []
        if not rows:
            break
        out.extend(rows)
        if len(rows) < PAGE_SIZE:
            break
        page += 1
        if page > 20:                  # hard cap
            break
    return out


async def _upsert(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO acled_events
            (event_id, event_date, event_type, sub_type,
             actor1, actor2, fatalities, lat, lon,
             district_id, state_code, notes, raw, inserted_at)
        VALUES
            (:event_id, :event_date, :event_type, :sub_type,
             :actor1, :actor2, :fatalities, :lat, :lon,
             :district_id, :state_code, :notes, CAST(:raw AS JSONB), now())
        ON CONFLICT (event_id) DO UPDATE SET
            event_date = EXCLUDED.event_date,
            event_type = EXCLUDED.event_type,
            sub_type   = EXCLUDED.sub_type,
            fatalities = EXCLUDED.fatalities,
            district_id= EXCLUDED.district_id,
            notes      = EXCLUDED.notes,
            raw        = EXCLUDED.raw
    """
    import json as _json
    written = 0
    async with get_db() as db:
        for r in rows:
            event_id = str(r.get("event_id_cnty") or r.get("data_id") or "").strip()
            if not event_id:
                continue
            ev_date = _safe_date(r.get("event_date"))
            if ev_date is None:
                continue
            lat = _safe_float(r.get("latitude"))
            lon = _safe_float(r.get("longitude"))
            district_id = (
                await district_for_lat_lon(db, lat, lon)
                or await district_for_name(db, r.get("admin2") or r.get("location"))
            )
            admin1 = (r.get("admin1") or "").lower()
            state_code = "TG" if "telangana" in admin1 else ("AP" if "andhra" in admin1 else None)
            try:
                await db.execute(
                    text(sql),
                    {
                        "event_id": event_id,
                        "event_date": ev_date,
                        "event_type": (r.get("event_type") or "Unknown")[:80],
                        "sub_type": (r.get("sub_event_type") or None),
                        "actor1": (r.get("actor1") or None),
                        "actor2": (r.get("actor2") or None),
                        "fatalities": _safe_int(r.get("fatalities")),
                        "lat": lat,
                        "lon": lon,
                        "district_id": district_id,
                        "state_code": state_code,
                        "notes": (r.get("notes") or "")[:2000],
                        "raw": _json.dumps(r),
                    },
                )
                written += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("acled upsert failed for %s: %s", event_id, exc)
                continue
        await db.commit()
    return written


async def _run() -> dict[str, int]:
    token = os.getenv("ACLED_ACCESS_TOKEN", "").strip()
    key = os.getenv("ACLED_API_KEY", "").strip() or None
    if not token:
        async with get_db() as db:
            await record_run_health(
                db, SOURCE_ID,
                success=False, error="ACLED_ACCESS_TOKEN not set",
            )
            await db.commit()
        return {"rows": 0, "skipped": True}

    total_rows: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        for adm1 in ADMIN1_FILTERS:
            try:
                rows = await _fetch_admin1(client, adm1, token, key)
                total_rows.extend(rows)
            except Exception as exc:  # noqa: BLE001
                logger.exception("acled fetch failed for %s", adm1)
                async with get_db() as db:
                    await record_run_health(db, SOURCE_ID, success=False, error=str(exc))
                    await db.commit()
                raise

    written = await _upsert(total_rows)
    async with get_db() as db:
        await record_run_health(db, SOURCE_ID, success=True, rows=written)
        await db.commit()
    logger.info("acled_sink: fetched=%d written=%d", len(total_rows), written)
    return {"fetched": len(total_rows), "rows": written}


@app.task(name="tasks.collectors.acled_sink", bind=True, max_retries=2)
def acled_sink(self) -> dict[str, int]:  # type: ignore[no-untyped-def]
    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("acled_sink failed")
        raise self.retry(exc=exc, countdown=900)
