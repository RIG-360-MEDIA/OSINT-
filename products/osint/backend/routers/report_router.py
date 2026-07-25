"""Daily State Intelligence Brief — preview JSON, PDF download, and email send."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from auth.middleware import get_optional_user
from brief_prefs import load_prefs
from db import get_db
import report_builder
import report_email
import report_render

router = APIRouter(prefix="/api/brief", tags=["brief"])


async def _build(user_id: str) -> dict[str, Any]:
    async with get_db() as db:
        prefs = await load_prefs(db, user_id)
        if not prefs:
            raise HTTPException(status_code=403, detail="No persona configured")
        return await report_builder.build_report(db, prefs)


@router.get("/report")
async def report_json(user: dict[str, str] | None = Depends(get_optional_user)) -> dict[str, Any]:
    """Structured report (for the Dispatch preview)."""
    if not user:
        raise HTTPException(status_code=401, detail="Not signed in")
    return await _build(user["id"])


@router.get("/report.pdf")
async def report_pdf(user: dict[str, str] | None = Depends(get_optional_user)) -> Response:
    """The Dispatch PDF now serves the REBUILT Daily Media Briefing (briefing.*),
    not the legacy report_builder brief. Renders the stored report to PDF via
    WeasyPrint so the existing frontend PDF viewer shows the new report with no
    frontend change."""
    if not user:
        raise HTTPException(status_code=401, detail="Not signed in")
    from datetime import datetime, timedelta, timezone
    from briefing.render import render_for
    from briefing.nightly import TELANGANA_ORG
    _IST = timezone(timedelta(hours=5, minutes=30))
    # newest briefing that actually exists, so the download never 404s on a
    # not-yet-generated day; falls back to yesterday if none found.
    from sqlalchemy import text
    from db import get_db
    async with get_db() as _db:
        _row = (await _db.execute(text("""
            SELECT ru.cover_date FROM briefing.report rp JOIN briefing.runs ru ON ru.id=rp.run_id
             WHERE ru.org_id = CAST(:o AS uuid) ORDER BY ru.cover_date DESC LIMIT 1
        """), {"o": TELANGANA_ORG})).fetchone()
    cover = _row.cover_date if _row else (
        datetime.now(timezone.utc).astimezone(_IST) - timedelta(days=1)).date()
    # Served from cache (rendered once/day); Chromium then WeasyPrint fallback.
    from briefing.cache import get_pdf
    try:
        pdf = await get_pdf(TELANGANA_ORG, cover)
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("report_router").warning(
            "chromium pdf failed (%s); falling back to weasyprint", str(exc)[:120])
        html = await render_for(TELANGANA_ORG, cover)
        from weasyprint import HTML as _HTML
        pdf = _HTML(string=html).write_pdf()
    if not pdf:
        raise HTTPException(status_code=404, detail=f"No briefing for {cover}")
    fname = f"Telangana-Media-Briefing-{cover}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{fname}"',
                             # the served day rolls forward each morning — never
                             # let a browser keep yesterday's cached PDF
                             "Cache-Control": "no-store, must-revalidate",
                             "Pragma": "no-cache", "Expires": "0"})


@router.post("/report/send")
async def report_send(
    to: str | None = Query(default=None, description="Override recipient; defaults to the signed-in user"),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    if not user:
        raise HTTPException(status_code=401, detail="Not signed in")
    recipient = (user.get("email") or "").strip()  # security: always self; to= override ignored
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
