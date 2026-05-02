"""
IMD weather warnings ingest. Free public XML at mausam.imd.gov.in.

Cadence: every hour. Source: the IMD nowcast/warning XML which lists
every state and the active alert for each district inside.

Per-district rows go into ``weather_warnings`` keyed by
(district_id, kind, valid_from). The endpoint shape changes
periodically (IMD has no API contract); the parser is defensive
and tolerates missing fields.

Severity heuristic:
  red    -> 'severe'
  orange -> 'high'
  yellow -> 'moderate'
  green  -> 'low'
"""

from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db
from backend.tasks.collectors._cm_helpers import district_for_name, record_run_health

logger = logging.getLogger(__name__)


SOURCE_ID = "imd_weather"
TIMEOUT_S = 25.0

# Two endpoints — the nowcast is the most actionable; the district
# warning XML covers a 5-day window. We hit both and union the rows.
NOWCAST_URL = "https://mausam.imd.gov.in/responsive/rss/nowcast.xml"
DISTRICT_WARNING_URL = "https://mausam.imd.gov.in/api/warnings_district_api.php"

TG_AP_STATES = {"telangana", "andhra pradesh"}

SEVERITY_MAP = {
    "red": "severe",
    "orange": "high",
    "yellow": "moderate",
    "green": "low",
}


def _severity(raw: str | None) -> str:
    if not raw:
        return "low"
    s = raw.lower().strip()
    for key, val in SEVERITY_MAP.items():
        if key in s:
            return val
    if "warn" in s:
        return "high"
    return "low"


async def _fetch_nowcast(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        resp = await client.get(NOWCAST_URL, headers={"User-Agent": "rig-cm-page/1.0"})
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("imd nowcast fetch failed: %s", exc)
        return out
    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError:
        logger.warning("imd nowcast: not parseable XML")
        return out
    # Typical RSS shape: channel/item with title=district, description=warning text.
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        desc = (item.findtext("description") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if not title:
            continue
        out.append({
            "district_name": title,
            "kind": "nowcast",
            "severity_raw": desc,
            "payload": desc[:1200],
            "valid_from_raw": pub,
        })
    return out


async def _fetch_district_warnings(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    """The 5-day district warning JSON. Shape: list of {state, district, day1..day5}."""
    out: list[dict[str, Any]] = []
    try:
        resp = await client.get(DISTRICT_WARNING_URL, headers={"User-Agent": "rig-cm-page/1.0"})
        resp.raise_for_status()
        rows = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("imd district warning fetch failed: %s", exc)
        return out
    if not isinstance(rows, list):
        return out
    today = datetime.now(timezone.utc).date()
    for r in rows:
        if not isinstance(r, dict):
            continue
        state = (r.get("State") or r.get("state") or "").lower()
        if not any(t in state for t in TG_AP_STATES):
            continue
        district = (r.get("District") or r.get("district") or "").strip()
        if not district:
            continue
        for offset in range(1, 6):
            color_key = f"Day{offset}_Color"
            text_key = f"Day{offset}"
            color = r.get(color_key) or r.get(color_key.lower())
            warn_text = r.get(text_key) or r.get(text_key.lower())
            if not color and not warn_text:
                continue
            valid_from = datetime.combine(today + timedelta(days=offset - 1), datetime.min.time(), tzinfo=timezone.utc)
            valid_to = valid_from + timedelta(hours=24)
            out.append({
                "district_name": district,
                "kind": "forecast",
                "severity_raw": color or "",
                "payload": (warn_text or color or "")[:1200],
                "valid_from": valid_from,
                "valid_to": valid_to,
            })
    return out


async def _run() -> dict[str, int]:
    written = 0
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        try:
            nowcast = await _fetch_nowcast(client)
            forecasts = await _fetch_district_warnings(client)
        except Exception as exc:  # noqa: BLE001
            logger.exception("imd fetch failed")
            async with get_db() as db:
                await record_run_health(db, SOURCE_ID, success=False, error=str(exc))
                await db.commit()
            raise

    rows = nowcast + forecasts
    if not rows:
        async with get_db() as db:
            await record_run_health(db, SOURCE_ID, success=True, rows=0)
            await db.commit()
        return {"rows": 0, "nowcast": 0, "forecast": 0}

    sql = """
        INSERT INTO weather_warnings
            (district_id, kind, severity, valid_from, valid_to, payload, recorded_at)
        VALUES
            (:district_id, :kind, :severity, :valid_from, :valid_to, :payload, now())
        ON CONFLICT (district_id, kind, valid_from) DO UPDATE SET
            severity = EXCLUDED.severity,
            valid_to = EXCLUDED.valid_to,
            payload  = EXCLUDED.payload,
            recorded_at = now()
    """
    async with get_db() as db:
        for r in rows:
            district_id = await district_for_name(db, r["district_name"])
            if not district_id:
                continue
            valid_from = r.get("valid_from") or datetime.now(timezone.utc)
            valid_to = r.get("valid_to") or (valid_from + timedelta(hours=6))
            try:
                await db.execute(
                    text(sql),
                    {
                        "district_id": district_id,
                        "kind": r["kind"],
                        "severity": _severity(r.get("severity_raw")),
                        "valid_from": valid_from,
                        "valid_to": valid_to,
                        "payload": r.get("payload") or "",
                    },
                )
                written += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("imd upsert failed: %s", exc)
                continue
        await record_run_health(db, SOURCE_ID, success=True, rows=written)
        await db.commit()
    logger.info("imd_weather: %d nowcast, %d forecast, %d upserted", len(nowcast), len(forecasts), written)
    return {"rows": written, "nowcast": len(nowcast), "forecast": len(forecasts)}


@app.task(name="tasks.collectors.imd_weather", bind=True, max_retries=2)
def imd_weather(self) -> dict[str, int]:  # type: ignore[no-untyped-def]
    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("imd_weather failed")
        raise self.retry(exc=exc, countdown=600)
