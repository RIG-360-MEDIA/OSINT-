"""Live endpoints for the rebuilt Daily Media Briefing.

  GET  /api/brief/media-briefing          -> rendered HTML (latest or ?date=)
  GET  /api/brief/media-briefing/json     -> the assembled report JSON
  POST /api/brief/media-briefing/run       -> trigger a full run for a date (admin)

Serves the STORED report (judged once, immutable) — no live rebuild per request.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import text

from db import get_db
from briefing.render import render_html
from briefing.nightly import run_full, TELANGANA_ORG

router = APIRouter(prefix="/api/brief", tags=["media-briefing"])
IST = timezone(timedelta(hours=5, minutes=30))


_NOCACHE = {"Cache-Control": "no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}


def _default_date() -> date:
    return (datetime.now(timezone.utc).astimezone(IST) - timedelta(days=1)).date()


async def _load_json(org_id: str, cover: date):
    async with get_db() as db:
        row = (await db.execute(text("""
            SELECT rp.json FROM briefing.report rp JOIN briefing.runs ru ON ru.id = rp.run_id
             WHERE ru.org_id = CAST(:o AS uuid) AND ru.cover_date = :d
        """), {"o": org_id, "d": cover})).fetchone()
        return row.json if row else None


async def _latest_date(org_id: str) -> date | None:
    """Most recent cover_date that actually has a rendered report — so the page
    shows the newest available briefing instead of a not-yet-generated day."""
    async with get_db() as db:
        row = (await db.execute(text("""
            SELECT ru.cover_date FROM briefing.report rp JOIN briefing.runs ru ON ru.id = rp.run_id
             WHERE ru.org_id = CAST(:o AS uuid) ORDER BY ru.cover_date DESC LIMIT 1
        """), {"o": org_id})).fetchone()
        return row.cover_date if row else None


@router.get("/media-briefing")
async def media_briefing_html(
    date: str | None = Query(default=None, description="YYYY-MM-DD; defaults to yesterday IST"),
    org: str = Query(default=TELANGANA_ORG),
) -> Response:
    cover = (await _latest_date(org) or _default_date()) if not date \
        else datetime.strptime(date, "%Y-%m-%d").date()
    from briefing.cache import get_html
    html = await get_html(org, cover)
    if not html:
        return Response(
            content=f"<html><body style='font-family:sans-serif;padding:40px'>"
                    f"<h2>No briefing yet for {cover}</h2>"
                    f"<p>It generates automatically each morning (~05:00 IST), "
                    f"or trigger it with POST /api/brief/media-briefing/run.</p></body></html>",
            media_type="text/html", headers=_NOCACHE)
    # never cache: the default date rolls forward each morning, so a cached copy
    # would keep showing the previous day's briefing after the nightly run.
    return Response(content=html, media_type="text/html", headers=_NOCACHE)


@router.get("/media-briefing/json")
async def media_briefing_json(
    date: str | None = Query(default=None),
    org: str = Query(default=TELANGANA_ORG),
):
    cover = (await _latest_date(org) or _default_date()) if not date \
        else datetime.strptime(date, "%Y-%m-%d").date()
    rep = await _load_json(org, cover)
    if not rep:
        raise HTTPException(status_code=404, detail=f"No briefing for {cover}")
    return rep


@router.post("/media-briefing/run")
async def media_briefing_run(
    date: str | None = Query(default=None),
    org: str = Query(default=TELANGANA_ORG),
    concurrency: int = Query(default=6, ge=1, le=12),
):
    cover = _default_date() if not date else datetime.strptime(date, "%Y-%m-%d").date()
    return await run_full(org, cover, concurrency=concurrency)


# ── Weekly (multi-day) rollup — same engine, aggregated across a date range.
# Rendered on request (no cache table yet): each call re-aggregates + re-runs
# the small LLM enrichment (big-story prose, quote translation, figure
# captions), so it's for periodic/report-pull use, not high-frequency polling.

def _week_range(start: str | None, end: str | None, days: int) -> tuple[date, date]:
    if start and end:
        return (datetime.strptime(start, "%Y-%m-%d").date(),
                datetime.strptime(end, "%Y-%m-%d").date())
    e = _default_date()  # yesterday IST — the newest fully-judged day
    s = e - timedelta(days=max(days, 1) - 1)
    return s, e


@router.get("/weekly-briefing")
async def weekly_briefing_html(
    start: str | None = Query(default=None, description="YYYY-MM-DD"),
    end: str | None = Query(default=None, description="YYYY-MM-DD"),
    days: int = Query(default=7, ge=1, le=31),
    org: str = Query(default=TELANGANA_ORG),
) -> Response:
    s, e = _week_range(start, end, days)
    from briefing.weekly_render import render_weekly_for
    html = await render_weekly_for(org, s, e)
    return Response(content=html, media_type="text/html", headers=_NOCACHE)


@router.get("/weekly-briefing/json")
async def weekly_briefing_json(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    days: int = Query(default=7, ge=1, le=31),
    org: str = Query(default=TELANGANA_ORG),
):
    s, e = _week_range(start, end, days)
    from briefing.weekly_assemble import assemble_weekly
    rep = await assemble_weekly(org, s, e)
    if rep.get("error"):
        raise HTTPException(status_code=404, detail=rep["error"])
    return rep


@router.get("/weekly-briefing.pdf")
async def weekly_briefing_pdf(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    days: int = Query(default=7, ge=1, le=31),
    org: str = Query(default=TELANGANA_ORG),
) -> Response:
    s, e = _week_range(start, end, days)
    from briefing.weekly_render import render_weekly_for
    from briefing.pdf import html_to_pdf
    html = await render_weekly_for(org, s, e)
    pdf = await html_to_pdf(html)
    fname = f"Telangana-Weekly-Media-Briefing-{s}-to-{e}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{fname}"', **_NOCACHE})
