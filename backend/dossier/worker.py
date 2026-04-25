"""Dossier worker — fan out to all eligible adapters in parallel.

Round 1: target → all adapters supporting `target_type`.
Round 2 (cascade): verified handles + emails harvested from round-1 findings →
username/email adapters. This turns "Narendra Modi" + a Wikidata-confirmed
@narendramodi handle into automatic WhatsMyName + Holehe enrichment.

Each adapter call is wrapped in asyncio.wait_for + try/except so a single dead
source can never poison the overall dossier. Status transitions:
    pending → running → (completed | partial | failed)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text

from backend.adapters.base import AdapterContext, AdapterSpec, Finding
from backend.adapters.registry import adapters_for
from backend.database import get_db

log = logging.getLogger(__name__)

_DEFAULT_PER_ADAPTER_TIMEOUT_S = 12.0
_MAX_CONCURRENT_ADAPTERS = 6
_MAX_CASCADE_HANDLES = 4              # cap fan-out so cascade can't explode
_LONG_TIMEOUT_ADAPTERS = {"gdelt"}    # adapters that get extra wait_for headroom

# Wikidata claim fields whose value IS a bare social handle.
_HANDLE_CLAIM_FIELDS = {"twitter", "instagram", "facebook", "github", "tiktok",
                        "youtube", "telegram", "linkedin", "reddit"}

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{2,40}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ── Public entry point ────────────────────────────────────────────────────────

async def run_dossier(
    *,
    dossier_id: UUID,
    target: str,
    target_type: str,
    purpose_note: str | None,
    allow_sensitive: bool,
) -> None:
    """Background task: collect findings + write to dossier_finding rows."""
    await _set_status(dossier_id, "running", started_at=datetime.utcnow())

    timeout_s = _per_adapter_timeout()
    ctx = AdapterContext(
        target=target,
        target_type=target_type,
        purpose_note=purpose_note,
        timeout_s=timeout_s,
    )
    specs = adapters_for(target_type, allow_sensitive=allow_sensitive)

    if not specs:
        await _set_status(
            dossier_id,
            "failed",
            error=f"no adapters available for target_type={target_type}",
            completed_at=datetime.utcnow(),
        )
        return

    sem = asyncio.Semaphore(_MAX_CONCURRENT_ADAPTERS)

    # ── Round 1 — direct fan-out ────────────────────────────────────────────
    results = await asyncio.gather(
        *(_safe_fetch_bounded(sem, s, ctx) for s in specs),
        return_exceptions=False,
    )

    all_findings: list[Finding] = []
    failed_sources: list[str] = []
    for spec, outcome in zip(specs, results):
        if isinstance(outcome, Exception):
            failed_sources.append(spec.name)
            continue
        all_findings.extend(outcome)

    # ── Round 2 — cascade on harvested handles/emails ────────────────────────
    cascade_findings, cascade_attempted, cascade_failed = await _cascade(
        sem=sem,
        base_findings=all_findings,
        allow_sensitive=allow_sensitive,
        timeout_s=timeout_s,
        origin=target,
    )
    all_findings.extend(cascade_findings)
    attempted_all = [s.name for s in specs] + cascade_attempted
    failed_sources.extend(cascade_failed)

    if all_findings:
        await _insert_findings(dossier_id, all_findings)

    summary = _build_summary(all_findings, attempted_all, failed_sources)
    final_status = (
        "failed" if not all_findings and failed_sources
        else ("partial" if failed_sources else "completed")
    )
    await _set_status(
        dossier_id,
        final_status,
        summary=summary,
        completed_at=datetime.utcnow(),
    )


# ── Cascade ──────────────────────────────────────────────────────────────────

async def _cascade(
    *,
    sem: asyncio.Semaphore,
    base_findings: list[Finding],
    allow_sensitive: bool,
    timeout_s: float,
    origin: str,
) -> tuple[list[Finding], list[str], list[str]]:
    """Harvest verified handles + emails from round-1 findings, fan out again."""
    handles, emails = _harvest_pivot_values(base_findings)
    if not handles and not emails:
        return [], [], []

    username_specs = adapters_for("username", allow_sensitive=allow_sensitive)
    email_specs = adapters_for("email", allow_sensitive=allow_sensitive)

    tasks: list[tuple[str, asyncio.Task[list[Finding]]]] = []
    attempted: list[str] = []

    for handle in handles[:_MAX_CASCADE_HANDLES]:
        if not _USERNAME_RE.match(handle):
            continue
        sub_ctx = AdapterContext(
            target=handle,
            target_type="username",
            purpose_note=f"cascade from {origin}",
            timeout_s=timeout_s,
        )
        for spec in username_specs:
            attempted.append(f"{spec.name}#{handle}")
            tasks.append((
                spec.name,
                asyncio.create_task(_safe_fetch_bounded(sem, spec, sub_ctx)),
            ))

    for email in emails[:_MAX_CASCADE_HANDLES]:
        if not _EMAIL_RE.match(email):
            continue
        sub_ctx = AdapterContext(
            target=email,
            target_type="email",
            purpose_note=f"cascade from {origin}",
            timeout_s=timeout_s,
        )
        for spec in email_specs:
            attempted.append(f"{spec.name}#{email}")
            tasks.append((
                spec.name,
                asyncio.create_task(_safe_fetch_bounded(sem, spec, sub_ctx)),
            ))

    if not tasks:
        return [], [], []

    findings: list[Finding] = []
    failed: list[str] = []
    for name, task in tasks:
        try:
            outcome = await task
            findings.extend(outcome)
        except Exception as exc:  # noqa: BLE001 — already wrapped, defensive
            log.warning("cascade task %s failed: %s", name, exc)
            failed.append(name)
    return findings, attempted, failed


def _harvest_pivot_values(findings: list[Finding]) -> tuple[list[str], list[str]]:
    """Pull bare social handles and email addresses out of round-1 findings.

    Wikidata emits findings whose `field` is the social platform name (e.g.
    "twitter", "instagram") and whose `value` is the bare handle string.
    """
    handles: list[str] = []
    emails: list[str] = []
    seen_h: set[str] = set()
    seen_e: set[str] = set()
    for f in findings:
        field = (f.field or "").lower()
        v = f.value
        # Some adapters put the handle in value['handle'] or value['username']
        if isinstance(v, dict):
            v = v.get("handle") or v.get("username") or v.get("user")
        if not isinstance(v, str):
            continue
        v = v.strip().lstrip("@")
        if field in _HANDLE_CLAIM_FIELDS:
            if v and v not in seen_h:
                handles.append(v)
                seen_h.add(v)
        elif field == "email" or field.endswith("_email"):
            if v and "@" in v and v not in seen_e:
                emails.append(v)
                seen_e.add(v)
    return handles, emails


# ── Adapter execution helpers ─────────────────────────────────────────────────

async def _safe_fetch_bounded(
    sem: asyncio.Semaphore, spec: AdapterSpec, ctx: AdapterContext
) -> list[Finding]:
    async with sem:
        return await _safe_fetch(spec, ctx)


async def _safe_fetch(spec: AdapterSpec, ctx: AdapterContext) -> list[Finding]:
    wait_timeout = _wait_timeout_for(spec.name, ctx.timeout_s)
    try:
        return await asyncio.wait_for(spec.fetch(ctx), timeout=wait_timeout)
    except asyncio.TimeoutError:
        log.warning(
            "adapter %s timed out for target=%s after %.1fs",
            spec.name, ctx.target, wait_timeout,
        )
        return []
    except Exception as exc:  # noqa: BLE001 — adapter failures must not poison run
        log.warning("adapter %s raised for target=%s: %s", spec.name, ctx.target, exc)
        return []


def _per_adapter_timeout() -> float:
    raw = os.environ.get("DOSSIER_PER_ADAPTER_TIMEOUT_S", "").strip()
    if raw:
        try:
            return max(float(raw), 5.0)
        except ValueError:
            log.warning("invalid DOSSIER_PER_ADAPTER_TIMEOUT_S=%r", raw)
    return _DEFAULT_PER_ADAPTER_TIMEOUT_S


def _wait_timeout_for(spec_name: str, ctx_timeout_s: float) -> float:
    """Outer asyncio.wait_for budget — must exceed the adapter's internal timeout."""
    if spec_name in _LONG_TIMEOUT_ADAPTERS:
        gdelt_raw = os.environ.get("DOSSIER_GDELT_TIMEOUT_S", "").strip()
        if gdelt_raw:
            try:
                return max(float(gdelt_raw), ctx_timeout_s) + 3.0
            except ValueError:
                pass
        return max(ctx_timeout_s, 25.0) + 3.0
    return ctx_timeout_s + 3.0


# ── Persistence ──────────────────────────────────────────────────────────────

async def _insert_findings(dossier_id: UUID, findings: list[Finding]) -> None:
    rows = [
        {
            "dossier_id": str(dossier_id),
            "source": f.source,
            "field": f.field,
            "value": json.dumps(f.value, default=str),
            "source_url": f.source_url,
            "confidence": float(f.confidence),
        }
        for f in findings
    ]
    async with get_db() as db:
        await db.execute(
            text(
                """
                INSERT INTO dossier_finding
                    (dossier_id, source, field, value, source_url, confidence)
                VALUES
                    (:dossier_id, :source, :field, CAST(:value AS jsonb),
                     :source_url, :confidence)
                """
            ),
            rows,
        )
        await db.commit()


async def _set_status(
    dossier_id: UUID,
    status: str,
    *,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    summary: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    sets = ["status = :status", "updated_at = NOW()"]
    params: dict[str, Any] = {"status": status, "id": str(dossier_id)}
    if started_at is not None:
        sets.append("started_at = :started_at")
        params["started_at"] = started_at
    if completed_at is not None:
        sets.append("completed_at = :completed_at")
        params["completed_at"] = completed_at
    if summary is not None:
        sets.append("summary = CAST(:summary AS jsonb)")
        params["summary"] = json.dumps(summary, default=str)
    if error is not None:
        sets.append("error = :error")
        params["error"] = error

    async with get_db() as db:
        await db.execute(
            text(f"UPDATE entity_dossier SET {', '.join(sets)} WHERE id = :id"),
            params,
        )
        await db.commit()


def _build_summary(
    findings: list[Finding],
    attempted: list[str],
    failed: list[str],
) -> dict[str, Any]:
    by_source: dict[str, int] = {}
    by_field: dict[str, int] = {}
    for f in findings:
        by_source[f.source] = by_source.get(f.source, 0) + 1
        by_field[f.field] = by_field.get(f.field, 0) + 1
    return {
        "total_findings": len(findings),
        "by_source": by_source,
        "by_field": by_field,
        "sources_attempted": attempted,
        "sources_failed": failed,
    }
