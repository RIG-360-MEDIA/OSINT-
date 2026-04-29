"""
Refresh the 7-day political-risk calendar.

Pulls upcoming dated events from govt_documents (court_listing,
parliament_business) and inserts them into cm_risk_calendar with a
risk_level computed by a light heuristic. Manual seed rows
(source_kind='manual_seed') are left untouched.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db

logger = logging.getLogger(__name__)

LOOKAHEAD_DAYS = 14


def _classify_risk(title: str, kind: str) -> str:
    t = (title or "").lower()
    if any(k in t for k in ("supreme court", "high court", "constitution bench")):
        return "high"
    if "no-confidence" in t or "no confidence" in t or "vote of confidence" in t:
        return "high"
    if "by-election" in t or "by-poll" in t or "by election" in t:
        return "high"
    if kind in {"court", "parliament"}:
        return "med"
    return "low"


async def _from_govt_documents() -> int:
    """Mine govt_documents for court / parliament dated events.
    Defensive: schema differs across forks, so we only insert when we can
    parse a date from the row."""
    sql = """
        SELECT id, title, document_type, source_name, published_at, intel_json
        FROM govt_documents
        WHERE document_type IN ('court_listing','parliament_business','parliament_bill')
          AND COALESCE(published_at, now()) > now() - interval '7 days'
        ORDER BY published_at DESC
        LIMIT 200
    """
    insert = """
        INSERT INTO cm_risk_calendar (
            event_date, kind, title, description, source_id, source_kind,
            source_url, risk_summary, risk_level, inserted_at, updated_at
        ) VALUES (
            :event_date, :kind, :title, :desc, :sid, 'govt_document',
            :url, :summary, :level, now(), now()
        )
        ON CONFLICT (event_date, kind, title, COALESCE(state, '')) DO UPDATE
            SET updated_at = now(),
                risk_level = EXCLUDED.risk_level,
                description = EXCLUDED.description
    """
    n = 0
    async with get_db() as db:
        try:
            rows = (await db.execute(text(sql))).all()
        except Exception as exc:  # noqa: BLE001
            logger.info("risk_window: govt_documents query skipped: %s", exc)
            return 0
        for r in rows:
            kind = "court" if "court" in (r.document_type or "") else "parliament"
            event_date = None
            if r.intel_json and isinstance(r.intel_json, dict):
                date_hint = r.intel_json.get("hearing_date") or r.intel_json.get("listed_on")
                if date_hint:
                    try:
                        event_date = date.fromisoformat(str(date_hint)[:10])
                    except (ValueError, TypeError):
                        event_date = None
            if event_date is None and r.published_at:
                event_date = r.published_at.date() + timedelta(days=2)
            if event_date is None:
                continue
            if event_date < date.today() or event_date > date.today() + timedelta(days=LOOKAHEAD_DAYS):
                continue
            await db.execute(
                text(insert),
                {
                    "event_date": event_date,
                    "kind": kind,
                    "title": (r.title or "")[:240],
                    "desc": (r.source_name or None),
                    "sid": r.id,
                    "url": None,
                    "summary": None,
                    "level": _classify_risk(r.title or "", kind),
                },
            )
            n += 1
        await db.commit()
    return n


@app.task(name="tasks.cm.refresh_risk_window", bind=True, max_retries=1)
def refresh_risk_window(self) -> dict[str, int]:
    try:
        n = asyncio.run(_from_govt_documents())
        return {"inserted_or_updated": n}
    except Exception as exc:
        logger.exception("refresh_risk_window failed")
        raise self.retry(exc=exc, countdown=900)
