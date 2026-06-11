"""Daily State Intelligence Brief — preview JSON, PDF download, and email send."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text

from auth.middleware import get_optional_user
from brief_prefs import load_prefs
from db import get_db
import report_builder
import report_email
import report_render

router = APIRouter(prefix="/api/brief", tags=["brief"])

# A report is a FIXED DAILY EDITION, not a live view: built once per user per edition day
# and frozen until the next day's edition. The edition rolls at 07:00 IST so the morning
# brief is the new day's and it never changes through the day on refresh/export.
_EDITION_SQL = "((analytics.now_sim() AT TIME ZONE 'Asia/Kolkata') - interval '7 hours')::date"


async def _build(user_id: str, force: bool = False) -> dict[str, Any]:
    """Serve today's frozen edition: return the cached build for the current edition day;
    only (re)build on a cache miss (or force), then freeze it so every later view is the same."""
    async with get_db() as db:
        ed = (await db.execute(text(f"SELECT {_EDITION_SQL} AS d"))).scalar()
        if not force:
            cached = (await db.execute(text(
                "SELECT report FROM analytics.report_cache "
                "WHERE user_id = CAST(:u AS uuid) AND edition_date = :d"
            ), {"u": user_id, "d": ed})).scalar()
            if cached:
                return cached
        prefs = await load_prefs(db, user_id)
        if not prefs:
            raise HTTPException(status_code=403, detail="No persona configured")
        r = await report_builder.build_report(db, prefs)
        try:  # caching is best-effort — never fail the request on a cache write
            await db.execute(text("""
                INSERT INTO analytics.report_cache (user_id, edition_date, report, built_at)
                VALUES (CAST(:u AS uuid), :d, CAST(:r AS jsonb), analytics.now_sim())
                ON CONFLICT (user_id, edition_date)
                DO UPDATE SET report = EXCLUDED.report, built_at = EXCLUDED.built_at
            """), {"u": user_id, "d": ed, "r": json.dumps(r, default=str)})
            await db.commit()
        except Exception:
            pass
        return r


@router.get("/report")
async def report_json(user: dict[str, str] | None = Depends(get_optional_user)) -> dict[str, Any]:
    """Structured report (for the Dispatch preview)."""
    if not user:
        raise HTTPException(status_code=401, detail="Not signed in")
    return await _build(user["id"])


@router.get("/report.pdf")
async def report_pdf(user: dict[str, str] | None = Depends(get_optional_user)) -> Response:
    if not user:
        raise HTTPException(status_code=401, detail="Not signed in")
    r = await _build(user["id"])
    pdf = report_render.render_pdf(r)
    fname = f"RIG-OSINT-{r['state_code']}-brief.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{fname}"'})


@router.post("/report/send")
async def report_send(
    to: str | None = Query(default=None, description="Override recipient; defaults to the signed-in user"),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    if not user:
        raise HTTPException(status_code=401, detail="Not signed in")
    recipient = (to or user.get("email") or "").strip()
    if not recipient:
        raise HTTPException(status_code=400, detail="No recipient email on file")
    r = await _build(user["id"])
    pdf = report_render.render_pdf(r)
    subject = f"RIG OSINT · {r['state']} Daily Brief · {str(r['generated_at'])[:10]}"
    body = (f"<p>Your daily <b>{r['state']}</b> intelligence brief is attached.</p>"
            f"<p>{r['kpis']['n24']} stories tracked · net sentiment {r['kpis']['net_sentiment']:+d}% · "
            f"confidence {r['confidence']}.</p><p style='color:#888'>— RIG OSINT Desk</p>")
    ok = report_email.send_report_email(recipient, subject, pdf, f"RIG-OSINT-{r['state_code']}-brief.pdf", body)
    if not ok:
        raise HTTPException(status_code=502, detail="Email send failed (SMTP not configured or rejected)")
    return {"sent": True, "to": recipient}
