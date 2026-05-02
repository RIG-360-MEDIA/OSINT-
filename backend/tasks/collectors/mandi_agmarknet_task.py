"""
AGMARKNET commodity prices ingest. Free public API via data.gov.in.

Cadence: every 4 hours. Source: data.gov.in resource
``9ef84268-d588-465a-a308-a864a43d0070`` (AGMARKNET retail / wholesale).

The endpoint returns up to 1000 records per call as JSON. We page
through filtering by state=Telangana / Andhra Pradesh and upsert into
``mandi_prices``. District is resolved by ``district_for_name`` against
the market column.

Env: DATA_GOV_IN_API_KEY (free, register at data.gov.in).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx
from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db
from backend.tasks.collectors._cm_helpers import district_for_name, record_run_health

logger = logging.getLogger(__name__)


SOURCE_ID = "mandi_agmarknet"
ENDPOINT = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
STATES = ("Telangana", "Andhra Pradesh")
TIMEOUT_S = 25.0
PAGE_SIZE = 500


def _to_paise_per_quintal(rupees_per_quintal: str | None) -> int | None:
    """AGMARKNET returns prices as strings in ₹/quintal. Convert to paise int."""
    if not rupees_per_quintal:
        return None
    try:
        return int(round(float(rupees_per_quintal) * 100))
    except (ValueError, TypeError):
        return None


async def _fetch_state(state: str, api_key: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    offset = 0
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        while True:
            params = {
                "api-key": api_key,
                "format": "json",
                "limit": PAGE_SIZE,
                "offset": offset,
                "filters[state]": state,
            }
            resp = await client.get(ENDPOINT, params=params)
            resp.raise_for_status()
            payload = resp.json()
            records = payload.get("records") or []
            out.extend(records)
            if len(records) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
            if offset > 5000:           # hard cap — never page forever
                break
    return out


async def _upsert(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO mandi_prices
            (market, district_id, state_code, commodity, variety, grade,
             min_price, max_price, modal_price, arrival_qty, recorded_at)
        VALUES
            (:market, :district_id, :state_code, :commodity, :variety, :grade,
             :min_price, :max_price, :modal_price, :arrival_qty, :recorded_at::date)
        ON CONFLICT (market, commodity, COALESCE(variety, ''), recorded_at) DO UPDATE SET
            district_id = EXCLUDED.district_id,
            min_price   = EXCLUDED.min_price,
            max_price   = EXCLUDED.max_price,
            modal_price = EXCLUDED.modal_price,
            arrival_qty = EXCLUDED.arrival_qty
    """
    written = 0
    async with get_db() as db:
        for r in rows:
            market = (r.get("market") or "").strip()
            commodity = (r.get("commodity") or "").strip()
            recorded_at = r.get("arrival_date") or r.get("price_date")
            if not (market and commodity and recorded_at):
                continue
            district_id = await district_for_name(db, market)
            state_str = (r.get("state") or "").lower()
            state_code = "TG" if "telangana" in state_str else ("AP" if "andhra" in state_str else None)
            if state_code is None:
                continue
            await db.execute(
                text(sql),
                {
                    "market": market,
                    "district_id": district_id,
                    "state_code": state_code,
                    "commodity": commodity,
                    "variety": (r.get("variety") or None),
                    "grade": (r.get("grade") or None),
                    "min_price": _to_paise_per_quintal(r.get("min_price")),
                    "max_price": _to_paise_per_quintal(r.get("max_price")),
                    "modal_price": _to_paise_per_quintal(r.get("modal_price")),
                    "arrival_qty": (
                        float(r["arrival"]) if r.get("arrival") else None
                    ),
                    "recorded_at": recorded_at,
                },
            )
            written += 1
        await record_run_health(db, SOURCE_ID, success=True, rows=written)
        await db.commit()
    return written


async def _run() -> dict[str, int]:
    api_key = os.getenv("DATA_GOV_IN_API_KEY", "").strip()
    if not api_key:
        async with get_db() as db:
            await record_run_health(
                db, SOURCE_ID,
                success=False, error="DATA_GOV_IN_API_KEY not set",
            )
            await db.commit()
        return {"rows": 0, "skipped": True}

    total = 0
    for state in STATES:
        try:
            records = await _fetch_state(state, api_key)
            total += await _upsert(records)
        except Exception as exc:  # noqa: BLE001
            logger.exception("mandi fetch failed for %s", state)
            async with get_db() as db:
                await record_run_health(db, SOURCE_ID, success=False, error=str(exc))
                await db.commit()
            raise
    return {"rows": total, "states": len(STATES)}


@app.task(name="tasks.collectors.mandi_agmarknet", bind=True, max_retries=2)
def mandi_agmarknet(self) -> dict[str, int]:  # type: ignore[no-untyped-def]
    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("mandi_agmarknet failed")
        raise self.retry(exc=exc, countdown=600)
