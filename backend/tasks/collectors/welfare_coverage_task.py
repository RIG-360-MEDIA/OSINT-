"""
Welfare-scheme coverage ingest. Mix of structured CKAN-style API
(``data.telangana.gov.in``) and brittle HTML scrape against the
state portals where APIs don't exist.

Cadence: daily.

Schemes V1 covers:
  - 'rythu_bandhu'      → farmer income support
  - 'kcr_kit'           → maternal-care kit
  - 'aasara_pensions'   → social-security pensions
  - 'kalyana_lakshmi'   → marriage assistance

Per-scheme strategy:
  rythu_bandhu : structured CKAN dataset (district-wise beneficiary).
                 TODO_SELECTOR_DATASET_ID below.
  kcr_kit      : scrape from health portal — TODO_SCRAPE.
  aasara       : scrape — TODO_SCRAPE.
  kalyana      : scrape — TODO_SCRAPE.

We persist into ``welfare_coverage`` keyed by
(scheme, district_id, recorded_at::date).

When a sub-source breaks the task records partial success — i.e. we
record health=success if AT LEAST one scheme produced rows; if all
fail we record failure.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, timezone
from typing import Any

import httpx
from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db
from backend.tasks.collectors._cm_helpers import district_for_name, record_run_health

logger = logging.getLogger(__name__)


SOURCE_ID = "welfare_coverage"
TIMEOUT_S = 30.0


# ── Rythu Bandhu (CKAN-style structured) ─────────────────────────────────


# TODO_SELECTOR_DATASET_ID: the actual resource id on
# data.telangana.gov.in. Keep this in env so it can be swapped without
# a code deploy when the dataset is re-published.
RYTHU_DATASET_RESOURCE = os.getenv(
    "RYTHU_BANDHU_RESOURCE_ID",
    "0000000-0000-0000-0000-000000000000",  # placeholder — must be set
)
DATA_TG_API = "https://data.telangana.gov.in/api/3/action/datastore_search"


async def _fetch_rythu_bandhu(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    if RYTHU_DATASET_RESOURCE.startswith("0000000"):
        logger.info("rythu_bandhu: RYTHU_BANDHU_RESOURCE_ID not set; skipping")
        return []
    try:
        resp = await client.get(
            DATA_TG_API,
            params={"resource_id": RYTHU_DATASET_RESOURCE, "limit": 100},
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("rythu_bandhu fetch failed: %s", exc)
        return []
    records = (payload.get("result") or {}).get("records") or []
    out: list[dict[str, Any]] = []
    for r in records:
        district = r.get("district") or r.get("District")
        beneficiaries = r.get("beneficiaries") or r.get("Beneficiaries")
        target = r.get("target") or r.get("Target")
        if not district:
            continue
        try:
            beneficiaries_n = int(float(beneficiaries)) if beneficiaries else 0
        except (ValueError, TypeError):
            beneficiaries_n = 0
        try:
            target_n = int(float(target)) if target else 0
        except (ValueError, TypeError):
            target_n = 0
        out.append({
            "scheme": "rythu_bandhu",
            "district_name": district,
            "beneficiaries": beneficiaries_n,
            "target": target_n,
        })
    return out


# ── Scraped schemes (kcr_kit / aasara / kalyana) ─────────────────────────


# TODO_SCRAPE: each of these schemes has a per-district beneficiary
# dashboard on a state portal. Implementations are intentionally
# stubbed to a no-op until the actual selectors are confirmed. We
# leave the shape so the persistence path below is exercised the
# moment a scrape goes live.
async def _fetch_kcr_kit(_client: httpx.AsyncClient) -> list[dict[str, Any]]:
    return []


async def _fetch_aasara(_client: httpx.AsyncClient) -> list[dict[str, Any]]:
    return []


async def _fetch_kalyana(_client: httpx.AsyncClient) -> list[dict[str, Any]]:
    return []


# ── Persistence ──────────────────────────────────────────────────────────


async def _upsert(rows: list[dict[str, Any]], today: date) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO welfare_coverage
            (scheme, district_id, beneficiaries, target,
             coverage_pct, recorded_at)
        VALUES
            (:scheme, :district_id, :beneficiaries, :target,
             :coverage_pct, :recorded_at)
        ON CONFLICT (scheme, district_id, recorded_at) DO UPDATE SET
            beneficiaries = EXCLUDED.beneficiaries,
            target        = EXCLUDED.target,
            coverage_pct  = EXCLUDED.coverage_pct
    """
    written = 0
    async with get_db() as db:
        for r in rows:
            district_id = await district_for_name(db, r.get("district_name"))
            if not district_id:
                continue
            target = r.get("target") or 0
            beneficiaries = r.get("beneficiaries") or 0
            pct = (beneficiaries / target * 100.0) if target > 0 else None
            try:
                await db.execute(
                    text(sql),
                    {
                        "scheme": r["scheme"],
                        "district_id": district_id,
                        "beneficiaries": beneficiaries,
                        "target": target,
                        "coverage_pct": pct,
                        "recorded_at": today,
                    },
                )
                written += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("welfare upsert failed: %s", exc)
                continue
        await db.commit()
    return written


async def _run() -> dict[str, int]:
    today = datetime.now(timezone.utc).date()
    fetched: list[dict[str, Any]] = []
    sub_errors: list[str] = []

    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        for label, fn in [
            ("rythu_bandhu", _fetch_rythu_bandhu),
            ("kcr_kit", _fetch_kcr_kit),
            ("aasara", _fetch_aasara),
            ("kalyana", _fetch_kalyana),
        ]:
            try:
                rows = await fn(client)
                fetched.extend(rows)
                logger.info("welfare:%s fetched %d rows", label, len(rows))
            except Exception as exc:  # noqa: BLE001
                logger.warning("welfare:%s failed: %s", label, exc)
                sub_errors.append(f"{label}: {exc}")

    written = await _upsert(fetched, today)

    success = written > 0
    err = None if success else ("all sub-sources empty: " + " | ".join(sub_errors[:3]))[:480]
    async with get_db() as db:
        await record_run_health(db, SOURCE_ID, success=success, rows=written, error=err)
        await db.commit()
    return {"rows": written, "sub_errors": len(sub_errors)}


@app.task(name="tasks.collectors.welfare_coverage", bind=True, max_retries=1)
def welfare_coverage(self) -> dict[str, int]:  # type: ignore[no-untyped-def]
    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("welfare_coverage failed")
        raise self.retry(exc=exc, countdown=900)
