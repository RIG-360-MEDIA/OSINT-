"""
TGSPDCL / TS-Transco power-grid status ingest.

NO public API. This is a brittle scrape against the TGSPDCL outage
dashboard + the State Load Despatch Centre PDF. We persist whatever
we can resolve into ``power_grid_status`` and degrade gracefully
when the upstream layout changes.

Cadence: every 30 minutes.

Health story:
  - On every run we record success / failure into source_run_health.
  - On parser failure we surface "stale > 24h" via the atlas-layer
    endpoint, so the UI badges the layer red rather than silently
    serving zero rows.

TODO_SELECTOR markers (search this file for them) tag the spots
that must be re-validated against the live page when it changes.
The current selectors target the public outage page at
``https://tgsouthernpower.org/`` and the SLDC daily report PDF at
``https://www.tssldc.co.in/sldcdr.php``.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db
from backend.tasks.collectors._cm_helpers import district_for_name, record_run_health

logger = logging.getLogger(__name__)


SOURCE_ID = "tgspdcl_power"
TIMEOUT_S = 25.0

# TODO_SELECTOR: confirm whenever TGSPDCL ships a redesign.
TGSPDCL_OUTAGE_URL = "https://tgsouthernpower.org/outagedetails"
SLDC_REPORT_URL = "https://www.tssldc.co.in/sldcdr.php"


# ── Outage scrape ────────────────────────────────────────────────────────


_OUTAGE_ROW = re.compile(
    # TODO_SELECTOR: TGSPDCL HTML structure. The real page renders the
    # list as a table where each <tr> looks roughly like:
    #   <td>district</td><td>circle</td><td>feeder</td>
    #   <td>start_time</td><td>restored_time</td><td>reason</td>
    # We use a relaxed regex over the row block to survive minor markup
    # changes; if this breaks, switch to BeautifulSoup with a CSS
    # selector against the actual id/class once they stop changing.
    r"<tr[^>]*>(.*?)</tr>",
    re.IGNORECASE | re.DOTALL,
)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return _TAG.sub("", s).strip()


async def _fetch_outage(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    """Scrape TGSPDCL outage list. Returns one row per outage entry."""
    try:
        resp = await client.get(
            TGSPDCL_OUTAGE_URL,
            headers={"User-Agent": "rig-cm-page/1.0 (research)"},
        )
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("tgspdcl outage fetch failed: %s", exc)
        return []

    out: list[dict[str, Any]] = []
    for tr_match in _OUTAGE_ROW.finditer(resp.text):
        cells = [_strip_html(td) for td in _TD.findall(tr_match.group(1))]
        # TODO_SELECTOR: column count + order may shift.
        if len(cells) < 4:
            continue
        district_name = cells[0]
        circle = cells[1] if len(cells) > 1 else None
        feeder = cells[2] if len(cells) > 2 else None
        reason = cells[5] if len(cells) > 5 else (cells[-1] if cells else None)
        out.append({
            "district_name": district_name,
            "circle": circle,
            "feeder": feeder,
            "reason": (reason or "")[:240],
        })
    return out


# ── SLDC daily despatch report (load / generation summary) ───────────────


async def _fetch_sldc(client: httpx.AsyncClient) -> dict[str, float | None]:
    """The SLDC report is a PDF — we don't parse it here. We fetch the
    landing page, look for the most recent demand/generation numbers
    in plain HTML if exposed, otherwise return None and let the per-
    district upsert proceed without the state-level totals."""
    try:
        resp = await client.get(
            SLDC_REPORT_URL,
            headers={"User-Agent": "rig-cm-page/1.0 (research)"},
        )
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("sldc fetch failed: %s", exc)
        return {"demand_mw": None, "supply_mw": None}

    # TODO_SELECTOR: SLDC page sometimes exposes demand / generation in
    # a small html table above the PDF link. The next two regexes look
    # for "Demand" / "Generation" lines and capture the integer / float
    # immediately after. If the layout changes to PDF-only, these will
    # both return None and we record only the outage rows.
    demand = None
    supply = None
    m_demand = re.search(r"Demand[^0-9]{0,40}([0-9,]{3,8})", resp.text, re.IGNORECASE)
    m_supply = re.search(r"Generation[^0-9]{0,40}([0-9,]{3,8})", resp.text, re.IGNORECASE)
    if m_demand:
        try:
            demand = float(m_demand.group(1).replace(",", ""))
        except ValueError:
            demand = None
    if m_supply:
        try:
            supply = float(m_supply.group(1).replace(",", ""))
        except ValueError:
            supply = None
    return {"demand_mw": demand, "supply_mw": supply}


# ── Persistence ──────────────────────────────────────────────────────────


async def _upsert(
    outages: list[dict[str, Any]],
    sldc: dict[str, float | None],
) -> int:
    sql = """
        INSERT INTO power_grid_status
            (district_id, recorded_at, demand_mw, supply_mw,
             outage_count, outage_reason)
        VALUES
            (:district_id, :recorded_at, :demand_mw, :supply_mw,
             :outage_count, :outage_reason)
        ON CONFLICT (district_id, recorded_at) DO UPDATE SET
            demand_mw     = EXCLUDED.demand_mw,
            supply_mw     = EXCLUDED.supply_mw,
            outage_count  = EXCLUDED.outage_count,
            outage_reason = EXCLUDED.outage_reason
    """
    written = 0
    now_ts = datetime.now(timezone.utc).replace(microsecond=0)
    # State-level demand / supply is identical across districts in this
    # crude V1; better is to read SLDC PDF per-area later.
    state_demand = sldc.get("demand_mw")
    state_supply = sldc.get("supply_mw")

    # Group outages by district.
    by_district: dict[str, list[str]] = {}
    async with get_db() as db:
        for o in outages:
            did = await district_for_name(db, o.get("district_name"))
            if not did:
                continue
            by_district.setdefault(did, []).append(o.get("reason") or "")

        for district_id, reasons in by_district.items():
            try:
                await db.execute(
                    text(sql),
                    {
                        "district_id": district_id,
                        "recorded_at": now_ts,
                        "demand_mw": state_demand,
                        "supply_mw": state_supply,
                        "outage_count": len(reasons),
                        "outage_reason": (" · ".join(r for r in reasons if r)[:240] or None),
                    },
                )
                written += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("tgspdcl upsert failed for %s: %s", district_id, exc)
                continue
        await db.commit()
    return written


async def _run() -> dict[str, int | None]:
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        try:
            outages = await _fetch_outage(client)
            sldc = await _fetch_sldc(client)
        except Exception as exc:  # noqa: BLE001
            logger.exception("tgspdcl scrape failed")
            async with get_db() as db:
                await record_run_health(db, SOURCE_ID, success=False, error=str(exc))
                await db.commit()
            raise

    written = await _upsert(outages, sldc)

    # If we got 0 rows, surface the failure via run-health so the layer
    # badges as stale rather than silently serving zeros.
    success = written > 0 or bool(outages)
    err = None if success else "no rows parsed — site layout likely changed"
    async with get_db() as db:
        await record_run_health(db, SOURCE_ID, success=success, rows=written, error=err)
        await db.commit()
    logger.info("tgspdcl_power: outages=%d upserted=%d", len(outages), written)
    return {"outages": len(outages), "rows": written, "demand_mw": sldc.get("demand_mw")}


@app.task(name="tasks.collectors.tgspdcl_power", bind=True, max_retries=1)
def tgspdcl_power(self) -> dict[str, int | None]:  # type: ignore[no-untyped-def]
    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("tgspdcl_power failed")
        raise self.retry(exc=exc, countdown=600)
