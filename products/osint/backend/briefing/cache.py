"""Cached render — the report HTML and PDF are rendered once per day and stored
in briefing.report (html/pdf columns), so the Dispatch page loads instantly
instead of re-rendering a 5.8 MB Chromium PDF on every request.

Cache is cleared whenever the report is re-assembled (assemble.py sets
pdf=NULL, html=NULL on upsert). nightly.run_full warms it after assembling.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from db import get_db

logger = logging.getLogger("briefing.cache")


async def _load(db, org_id, cover):
    return (await db.execute(text("""
        SELECT rp.run_id, rp.json, rp.html, rp.pdf
          FROM briefing.report rp JOIN briefing.runs ru ON ru.id = rp.run_id
         WHERE ru.org_id = CAST(:o AS uuid) AND ru.cover_date = :d
    """), {"o": org_id, "d": cover})).fetchone()


async def get_html(org_id: str, cover) -> str | None:
    async with get_db() as db:
        row = await _load(db, org_id, cover)
        if not row:
            return None
        if row.html:
            return row.html
        from briefing.render import render_html
        html = render_html(row.json)
        await db.execute(text("UPDATE briefing.report SET html=:h WHERE run_id=:r"),
                         {"h": html, "r": row.run_id})
        await db.commit()
        return html


async def get_pdf(org_id: str, cover) -> bytes | None:
    async with get_db() as db:
        row = await _load(db, org_id, cover)
        if not row:
            return None
        if row.pdf:
            return bytes(row.pdf)
        from briefing.render import render_html
        from briefing.pdf import html_to_pdf
        html = row.html or render_html(row.json)
        pdf = await html_to_pdf(html)
        await db.execute(text("UPDATE briefing.report SET pdf=:p, html=:h WHERE run_id=:r"),
                         {"p": pdf, "h": html, "r": row.run_id})
        await db.commit()
        logger.info("cached PDF for %s (%d bytes)", cover, len(pdf))
        return pdf
