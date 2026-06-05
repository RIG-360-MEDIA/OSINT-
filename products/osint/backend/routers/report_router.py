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
