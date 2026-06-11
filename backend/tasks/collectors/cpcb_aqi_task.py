"""
CPCB live AQI ingest. Free public endpoint at app.cpcbccr.com.

Cadence: every 30 minutes. Fetches every TG/AP station's latest reading
and upserts into ``air_quality_readings``.

Station-to-district mapping uses ``district_for_name`` (matches against
the city in the station name; falls back to lat/lon centroid lookup
when the JSON includes coordinates).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
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


SOURCE_ID = "cpcb_aqi"
TIMEOUT_S = 20.0

# CPCB exposes a JSON list of all live stations at this endpoint. The
# response shape can drift across CPCB redesigns; the parser is
# defensive and skips rows it doesn't recognise.
ENDPOINT = "https://app.cpcbccr.com/caaqms/caaqms_landing"
TG_AP_STATES = {"telangana", "andhra pradesh"}


def _aqi_category(aqi: int | None) -> str | None:
    if aqi is None:
        return None
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Satisfactory"
    if aqi <= 200:
        return "Moderate"
    if aqi <= 300:
        return "Poor"
    if aqi <= 400:
        return "Very Poor"
    return "Severe"


def _safe_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None and v != "" else None
    except (ValueError, TypeError):
        return None


def _safe_int(v: Any) -> int | None:
    f = _safe_float(v)
    return int(round(f)) if f is not None else None


async def _fetch_landing(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    resp = await client.get(ENDPOINT, headers={"User-Agent": "rig-cm-page/1.0"})
    resp.raise_for_status()
    data = resp.json()
    # CPCB landing returns either a list directly or a dict with key "stations".
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("stations") or data.get("data") or []
    return []


async def _run() -> dict[str, int]:
    written = 0
    seen_in_states = 0
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S, follow_redirects=True) as client:
            stations = await _fetch_landing(client)
    except Exception as exc:  # noqa: BLE001
        logger.exception("cpcb landing fetch failed")
        async with get_db() as db:
            await record_run_health(db, SOURCE_ID, success=False, error=str(exc))
            await db.commit()
        raise

    upsert_sql = """
        INSERT INTO air_quality_readings
            (station, station_code, district_id, state_code,
             aqi, aqi_category, pm25, pm10, no2, so2, co, o3, recorded_at)
        VALUES
            (:station, :station_code, :district_id, :state_code,
             :aqi, :aqi_category, :pm25, :pm10, :no2, :so2, :co, :o3, :recorded_at)
        ON CONFLICT (station, recorded_at) DO UPDATE SET
            district_id  = EXCLUDED.district_id,
            aqi          = EXCLUDED.aqi,
            aqi_category = EXCLUDED.aqi_category,
            pm25         = EXCLUDED.pm25,
            pm10         = EXCLUDED.pm10,
            no2          = EXCLUDED.no2,
            so2          = EXCLUDED.so2,
            co           = EXCLUDED.co,
            o3           = EXCLUDED.o3
    """
    async with get_db() as db:
        for s in stations:
            if not isinstance(s, dict):
                continue
            state_str = (s.get("state") or "").lower()
            if not any(t in state_str for t in TG_AP_STATES):
                continue
            seen_in_states += 1
            station_name = s.get("station") or s.get("station_name") or ""
            if not station_name:
                continue
            state_code = "TG" if "telangana" in state_str else "AP"
            lat = _safe_float(s.get("latitude") or s.get("lat"))
            lon = _safe_float(s.get("longitude") or s.get("lon"))
            district_id = (
                await district_for_name(db, s.get("city") or station_name)
                or await district_for_lat_lon(db, lat, lon)
            )
            recorded_at_str = s.get("last_update") or s.get("updated_at")
            try:
                recorded_at = (
                    datetime.fromisoformat(recorded_at_str.replace("Z", "+00:00"))
                    if recorded_at_str else datetime.now(timezone.utc)
                )
            except (ValueError, AttributeError):
                recorded_at = datetime.now(timezone.utc)
            aqi = _safe_int(s.get("aqi") or s.get("AQI"))
            try:
                await db.execute(
                    text(upsert_sql),
                    {
                        "station": station_name,
                        "station_code": s.get("station_id") or s.get("code"),
                        "district_id": district_id,
                        "state_code": state_code,
                        "aqi": aqi,
                        "aqi_category": _aqi_category(aqi),
                        "pm25": _safe_float(s.get("pm25") or s.get("PM2.5")),
                        "pm10": _safe_float(s.get("pm10") or s.get("PM10")),
                        "no2": _safe_float(s.get("no2") or s.get("NO2")),
                        "so2": _safe_float(s.get("so2") or s.get("SO2")),
                        "co": _safe_float(s.get("co") or s.get("CO")),
                        "o3": _safe_float(s.get("o3") or s.get("O3")),
                        "recorded_at": recorded_at,
                    },
                )
                written += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("cpcb upsert failed for station %s: %s", station_name, exc)
                continue
        await record_run_health(db, SOURCE_ID, success=True, rows=written)
        await db.commit()
    logger.info("cpcb_aqi: %d stations (TG/AP), %d upserted", seen_in_states, written)
    return {"stations_in_state": seen_in_states, "rows": written}


@app.task(name="tasks.collectors.cpcb_aqi", bind=True, max_retries=2)
def cpcb_aqi(self) -> dict[str, int]:  # type: ignore[no-untyped-def]
    # DISABLED 2026-06-08: upstream CPCB source decommissioned. app.cpcbccr.com
    # now 301-redirects every data path (caaqms_landing, caaqms_landing_data,
    # aqi_all_Parameters) to aqinow.org -- an unverified third-party domain whose
    # data endpoints 404. Repointing at it would ingest from an untrusted source,
    # so this task is a no-op until re-implemented against a verified CPCB AQI
    # endpoint. Returning cleanly (no retry) stops the 404 failure storm.
    logger.warning(
        "cpcb_aqi disabled: source decommissioned (app.cpcbccr.com -> aqinow.org, "
        "data paths 404). No-op until re-implemented against a verified source."
    )
    return {"stations_in_state": 0, "rows": 0}
