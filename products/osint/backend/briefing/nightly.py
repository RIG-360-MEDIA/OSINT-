"""Nightly briefing runner — full pipeline for the previous IST calendar day.

Started at app boot (mirrors home_cache.start_scheduler): an asyncio loop that,
once per day in the 05:00-05:59 IST window, runs the whole chain for yesterday
(IST): judge -> merge -> assemble -> store report JSON. Idempotent/resumable —
run_day skips already-judged items, so a partial night resumes cleanly.

Also exposes run_full() for on-demand triggering from the router.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from briefing.pipeline import run_day
from briefing.merge import merge_events
from briefing.assemble import assemble

logger = logging.getLogger("briefing.nightly")

IST = timezone(timedelta(hours=5, minutes=30))
TELANGANA_ORG = "31ad3fa9-25eb-4b3c-8a56-360696fc680a"
# Orgs to generate a daily briefing for. Multi-tenant: add org ids here.
ACTIVE_ORGS = [TELANGANA_ORG]


async def run_full(org_id: str, cover_date, concurrency: int = 6) -> dict:
    """judge -> merge -> assemble for one org+day. Returns summary."""
    logger.info("briefing run_full %s %s", org_id, cover_date)
    jud = await run_day(org_id, cover_date, limit_per_pillar=2000, concurrency=concurrency)
    mrg = await merge_events(org_id, cover_date)
    rep = await assemble(org_id, cover_date)
    # warm the HTML + PDF cache so the first Dispatch load of the day is instant
    try:
        from briefing.cache import get_pdf
        await get_pdf(org_id, cover_date)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pdf cache warm failed: %s", str(exc)[:120])
    strip = rep.get("strip", {})
    summary = {"cover_date": str(cover_date), "judged": jud.get("total"),
               "about_government": jud.get("about_government"),
               "events": mrg.get("events"),
               "net": strip.get("sentiment", {}).get("net")}
    logger.info("briefing done: %s", summary)
    return summary


def _yesterday_ist() -> "datetime.date":
    now_ist = datetime.now(timezone.utc).astimezone(IST)
    return (now_ist - timedelta(days=1)).date()


async def _loop() -> None:
    ran_for: set = set()
    while True:
        try:
            now_ist = datetime.now(timezone.utc).astimezone(IST)
            cover = _yesterday_ist()
            key = str(cover)
            # fire once in the 05:00-05:59 IST window per cover date
            if now_ist.hour == 5 and key not in ran_for:
                ran_for.add(key)
                for org in ACTIVE_ORGS:
                    try:
                        await run_full(org, cover)
                    except Exception as exc:  # noqa: BLE001
                        logger.error("nightly run failed for %s: %s", org, str(exc)[:200])
            # keep the set small
            if len(ran_for) > 8:
                ran_for = set(list(ran_for)[-4:])
        except Exception as exc:  # noqa: BLE001
            logger.warning("nightly loop tick error: %s", str(exc)[:160])
        await asyncio.sleep(20 * 60)  # check every 20 min


def start_briefing_scheduler() -> asyncio.Task:
    """Launch the nightly loop as a background task. Call once at app startup."""
    logger.info("briefing nightly scheduler started (fires ~05:00 IST)")
    return asyncio.create_task(_loop())
