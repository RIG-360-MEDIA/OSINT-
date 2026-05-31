"""GET /api/brief/export — deliverable artifacts (Category-4).

`?format=onepager|html|csv|compose` (compose adds `?channel=email|slack|whatsapp`).
Per-recipient by construction. LLM-free by default; `?include_prose=true` folds in
a BLUF + situation-room line. Returns the rendered artifact; actual sending is a
separate credential-gated connector.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Query

from auth.middleware import get_optional_user
from brief_prefs import load_prefs
from db import get_db
from mailer import MailNotConfigured, send_gmail
from render import CHANNELS, compose, export_csv, gather_brief, newsletter_html, one_pager_text
from textual import compute_textual

router = APIRouter(prefix="/api/brief", tags=["brief"])


@router.get("/export")
async def get_export(
    format: str = Query(default="onepager"),
    channel: str = Query(default="email"),
    window_hours: int = Query(default=504, ge=24, le=2160),
    include_prose: bool = Query(default=False),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"]) if user else None
        if not prefs:
            return {"personalized": False, "artifact": None}
        prose = None
        if include_prose:
            t = await compute_textual(db, prefs, window_hours, ["executive_bluf", "situation_room"])
            prose = t.get("features")
        brief = await gather_brief(db, prefs, window_hours, prose)
        subject = brief.get("subject")
        if format == "html":
            return {"format": "html", "subject": subject, "artifact": newsletter_html(brief)}
        if format == "csv":
            return {"format": "csv", "subject": subject, "artifact": export_csv(brief)}
        if format == "compose":
            return {"format": "compose", "subject": subject,
                    "channels": {c: compose(brief, c) for c in CHANNELS},
                    "requested": compose(brief, channel) if channel in CHANNELS else None}
        return {"format": "onepager", "subject": subject, "artifact": one_pager_text(brief)}


@router.get("/send_test")
async def send_test(
    to: str = Query(..., description="recipient email"),
    dry_run: bool = Query(default=True, description="true = render only, do not send"),
    window_hours: int = Query(default=504, ge=24, le=2160),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    """Render the user's brief and (only when dry_run=false) email it via Gmail.
    Defaults to dry-run so a real send is always a deliberate call."""
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"]) if user else None
        if not prefs:
            return {"sent": False, "reason": "no prefs"}
        brief = await gather_brief(db, prefs, window_hours)
        subject = f"Situation Brief — {brief.get('subject')}"
        html, text = newsletter_html(brief), one_pager_text(brief)
        if dry_run:
            return {"dry_run": True, "to": to, "subject": subject, "preview": text[:1200]}
        try:
            return await asyncio.to_thread(send_gmail, to, subject, html, text)
        except MailNotConfigured as e:
            return {"sent": False, "error": str(e),
                    "hint": "set GMAIL_ADDRESS + GMAIL_APP_PASSWORD in the osint-backend .env, then restart"}
        except Exception as e:  # noqa: BLE001
            return {"sent": False, "error": str(e)[:200]}
