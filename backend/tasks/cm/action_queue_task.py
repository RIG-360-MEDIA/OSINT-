"""
For-the-Chair action queue, populated every 15 minutes.

Hybrid generator:

  RULE-BASED (deterministic, always trusted, no LLM):
    - Counter-narrative window opening:
        Trigger: any cm_counter_narratives row in the last 6 hours
        with rejected = FALSE — implies the LLM has produced a usable
        counter draft for an open issue. Action P0: 'Counter [issue]
        narrative within 6h'.
    - Calendar event in the next 36 hours:
        Trigger: cm_risk_calendar row with event_date <= NOW + 36h
        and risk_level >= MEDIUM. Action P1: 'Field statement before
        [event]'.
    - High-severity dissent surfaced today:
        Trigger: cm_dissent_signals.detected_at > NOW - 6h AND
        severity >= 0.7. Action P1: 'Address intra-coalition
        contradiction on [issue]'.

  LLM-PROPOSED (with cite_ids — best-effort):
    Asks Groq for one or two more action items based on today's hottest
    signals. Cite-IDs validated; rejected items are dropped. (Not
    persisted as 'rejected' rows — actions are idempotent re-runs of
    rules, so a rejected LLM action just doesn't insert.)

Each action carries:
  - priority (P0/P1/P2)
  - text (one operative sentence)
  - deadline (display string)
  - source_type ('rule' / 'llm' / 'calendar')
  - rule_name (for dedup; allows the rule to re-run idempotently)
  - cite_ids (UUID[] of articles, when source_type='llm')
  - expires_at (auto-aging)

Dedup is enforced by an INSERT … WHERE NOT EXISTS guard on
(state, source_type, rule_name, text) for active rows.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db
from backend.nlp.cm.cite_validate import validate_cite_ids

logger = logging.getLogger(__name__)


DEFAULT_TTL_HOURS = 24


def _expires_in(hours: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


# ── RULE-BASED action generators ─────────────────────────────────────────


async def _rule_counter_narrative(state: str | None) -> list[dict[str, Any]]:
    """One P0 action per recent counter-narrative draft."""
    sql = """
        SELECT cn.id, cn.issue_id, i.label
        FROM cm_counter_narratives cn
        LEFT JOIN cm_issues i ON i.id = cn.issue_id
        WHERE cn.state = COALESCE(:state, cn.state)
          AND cn.generated_at > NOW() - INTERVAL '6 hours'
          AND cn.rejected = FALSE
        ORDER BY cn.generated_at DESC
        LIMIT 5
    """
    async with get_db() as db:
        rows = (await db.execute(text(sql), {"state": state})).all()
    out: list[dict[str, Any]] = []
    for r in rows:
        label = r.label or "open issue"
        out.append({
            "priority": "P0",
            "text": f"Counter the {label} narrative within 6h.",
            "deadline": "within 6h",
            "source_type": "rule",
            "rule_name": f"counter_narrative:{r.id}",
            "cite_ids": [],
            "expires_at": _expires_in(8),
        })
    return out


async def _rule_calendar_event(state: str | None) -> list[dict[str, Any]]:
    sql = """
        SELECT id, event_date, kind, title, risk_level
        FROM cm_risk_calendar
        WHERE state = COALESCE(:state, state)
          AND event_date >= CURRENT_DATE
          AND event_date <= CURRENT_DATE + INTERVAL '2 days'
          AND COALESCE(UPPER(risk_level), 'LOW') IN ('MED', 'HIGH', 'MEDIUM')
        ORDER BY event_date ASC
        LIMIT 5
    """
    async with get_db() as db:
        rows = (await db.execute(text(sql), {"state": state})).all()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append({
            "priority": "P1",
            "text": f"Pre-empt {r.title} ({r.event_date.strftime('%-d %b') if r.event_date else 'soon'}).",
            "deadline": f"before {r.event_date.strftime('%-d %b') if r.event_date else 'event'}",
            "source_type": "calendar",
            "rule_name": f"calendar_event:{r.id}",
            "cite_ids": [],
            "expires_at": _expires_in(36),
        })
    return out


async def _rule_dissent_signal(state: str | None) -> list[dict[str, Any]]:
    sql = """
        SELECT ds.id, i.label, ds.severity
        FROM cm_dissent_signals ds
        LEFT JOIN cm_issues i ON i.id = ds.issue_id
        WHERE ds.state = COALESCE(:state, ds.state)
          AND ds.detected_at > NOW() - INTERVAL '6 hours'
          AND ds.severity::numeric >= 0.7
        ORDER BY ds.severity DESC
        LIMIT 3
    """
    async with get_db() as db:
        rows = (await db.execute(text(sql), {"state": state})).all()
    out: list[dict[str, Any]] = []
    for r in rows:
        label = r.label or "the open issue"
        out.append({
            "priority": "P1",
            "text": f"Address intra-coalition contradiction on {label}.",
            "deadline": "within 24h",
            "source_type": "rule",
            "rule_name": f"dissent:{r.id}",
            "cite_ids": [],
            "expires_at": _expires_in(24),
        })
    return out


# ── LLM-PROPOSED action generator ────────────────────────────────────────


LLM_ACTION_PROMPT = (
    "You are the chief of staff for the Chief Minister of {state}. Given the "
    "intelligence signals below, propose 0-2 concrete operative actions for "
    "the chair to consider in the NEXT 24 HOURS. Each action must:\n"
    "  - be a single sentence in imperative voice (e.g. 'Visit Khammam this week.')\n"
    "  - cite at least 1 article id from the signals as cite_ids\n"
    "  - have priority P0 (urgent), P1 (today), or P2 (this week)\n"
    "  - have a deadline phrase (e.g. 'within 6h', 'before Sunday rally')\n\n"
    "Return raw JSON: {{\"actions\": [ {{\"priority\":..., \"text\":..., "
    "\"deadline\":..., \"cite_ids\":[\"<uuid>\", ...]}} ]}}\n\n"
    "Signals:\n{signals}"
)


async def _llm_actions(state: str | None) -> list[dict[str, Any]]:
    sql = """
        SELECT a.id, a.title, COALESCE(a.lead_text_translated, a.lead_text_original, '') AS body
        FROM articles a
        JOIN article_districts ad ON ad.article_id = a.id AND ad.is_primary = TRUE
        JOIN districts d ON d.id = ad.district_id
        WHERE a.collected_at > NOW() - INTERVAL '12 hours'
          AND a.nlp_processed = TRUE
          AND a.is_duplicate = FALSE
          AND d.state_code = COALESCE(:state, d.state_code)
        ORDER BY a.collected_at DESC
        LIMIT 12
    """
    async with get_db() as db:
        rows = (await db.execute(text(sql), {"state": state})).all()
    if not rows:
        return []
    signals_text = "\n".join(
        f"- id={r.id} · {r.title} — {(r.body or '')[:240]}" for r in rows
    )
    try:
        from backend.nlp.groq_client import call_groq, FAST_MODEL
    except ImportError:
        return []
    prompt = LLM_ACTION_PROMPT.format(
        state="Telangana" if state == "TG" else (state or "the state"),
        signals=signals_text,
    )
    try:
        resp = await call_groq(system="Return raw JSON only.", user=prompt, model=FAST_MODEL)
    except Exception as exc:  # noqa: BLE001
        logger.warning("groq action call failed: %s", exc)
        return []
    if not resp:
        return []
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp.strip(), flags=re.IGNORECASE | re.MULTILINE).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    items = parsed.get("actions") or []
    if not isinstance(items, list):
        return []

    out: list[dict[str, Any]] = []
    for it in items[:3]:
        if not isinstance(it, dict):
            continue
        priority = it.get("priority")
        text_blob = it.get("text") or ""
        deadline = it.get("deadline") or ""
        cite_ids_raw = it.get("cite_ids") or []
        if priority not in {"P0", "P1", "P2"}:
            continue
        if not text_blob.strip() or len(text_blob) > 240:
            continue
        # Validate cite ids
        valid: list[UUID] = []
        for c in cite_ids_raw:
            try:
                valid.append(UUID(str(c).strip()))
            except (ValueError, TypeError):
                continue
        if not valid:
            continue
        async with get_db() as db:
            v = await validate_cite_ids(db, valid)
        if not v.all_valid:
            logger.info("llm action dropped — cite-id validation failed")
            continue
        out.append({
            "priority": priority,
            "text": text_blob.strip()[:240],
            "deadline": deadline.strip()[:60],
            "source_type": "llm",
            "rule_name": None,
            "cite_ids": v.valid_ids,
            "expires_at": _expires_in(24),
        })
    return out


# ── Persist (idempotent dedup) ───────────────────────────────────────────


async def _persist_actions(state: str | None, actions: list[dict[str, Any]]) -> int:
    """Insert each action only if no active row with the same dedup key
    already exists. Returns count of new rows."""
    insert_sql = """
        INSERT INTO cm_action_queue
            (state_code, priority, text, deadline, source_type, rule_name,
             cite_ids, generated_at, expires_at, status)
        SELECT :state, :priority, :text, :deadline, :source_type, :rule_name,
               CAST(:cites AS uuid[]), now(), :expires_at, 'active'
        WHERE NOT EXISTS (
            SELECT 1 FROM cm_action_queue
            WHERE state_code = :state
              AND source_type = :source_type
              AND COALESCE(rule_name, '') = COALESCE(:rule_name, '')
              AND text = :text
              AND status = 'active'
        )
        RETURNING id
    """
    written = 0
    async with get_db() as db:
        for a in actions:
            cites = [str(u) for u in (a.get("cite_ids") or [])]
            row = (await db.execute(
                text(insert_sql),
                {
                    "state": state or "TG",
                    "priority": a["priority"],
                    "text": a["text"],
                    "deadline": a.get("deadline"),
                    "source_type": a["source_type"],
                    "rule_name": a.get("rule_name"),
                    "cites": cites,
                    "expires_at": a["expires_at"],
                },
            )).first()
            if row:
                written += 1
        # Auto-expire stale rows.
        await db.execute(
            text("""
                UPDATE cm_action_queue SET status = 'expired'
                WHERE status = 'active' AND expires_at < NOW()
            """)
        )
        await db.commit()
    return written


async def _run(state: str | None) -> dict[str, int]:
    rule_actions = (
        await _rule_counter_narrative(state)
        + await _rule_calendar_event(state)
        + await _rule_dissent_signal(state)
    )
    llm_actions = await _llm_actions(state)
    new_count = await _persist_actions(state, rule_actions + llm_actions)
    return {
        "rule_proposed": len(rule_actions),
        "llm_proposed": len(llm_actions),
        "inserted": new_count,
    }


@app.task(name="tasks.cm.action_queue", bind=True, max_retries=1)
def action_queue(self, state: str = "TG") -> dict[str, int]:  # type: ignore[no-untyped-def]
    try:
        return asyncio.run(_run(state))
    except Exception as exc:
        logger.exception("action_queue failed")
        raise self.retry(exc=exc, countdown=300)
