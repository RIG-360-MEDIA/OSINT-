"""backend.draftsmith.db._flags — rigwire.draft_flags CRUD (per-claim editor review)."""
from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import text

from backend.database import get_db
from backend.draftsmith._db_serialize import flag_from_row
from backend.draftsmith.db._common import DraftsmithDBError
from backend.draftsmith.models import Flag


async def create_flags(job_id: str, version_id: str, flags: Sequence[Flag]) -> list[Flag]:
    if not flags:
        return []
    created: list[Flag] = []
    async with get_db() as session:
        for flag in flags:
            result = await session.execute(
                text(
                    """
                    INSERT INTO rigwire.draft_flags (
                        job_id, version_id, beat_index, span, severity, reason, source_ids
                    ) VALUES (
                        :job_id, :version_id, :beat_index, :span, :severity, :reason, :source_ids
                    )
                    RETURNING *
                    """
                ),
                {
                    "job_id": job_id,
                    "version_id": version_id,
                    "beat_index": flag.beat_index,
                    "span": flag.span,
                    "severity": flag.severity,
                    "reason": flag.reason,
                    "source_ids": list(flag.source_ids),
                },
            )
            row = result.mappings().first()
            if row is not None:
                created.append(flag_from_row(row))
        await session.commit()
    return created


async def resolve_flag(
    flag_id: str, action: str, editor_id: str, note: Optional[str] = None,
) -> Flag:
    """Transitions exactly one flag out of 'open'. This function only ever
    issues a single-row UPDATE, so it can never itself trip the DB's
    draft_flags_single_resolve statement-level guard against bulk-resolve."""
    if action not in ("dismissed", "fixed"):
        raise DraftsmithDBError(
            f"resolve_flag: action must be 'dismissed' or 'fixed', got {action!r}"
        )
    if not editor_id or "@" not in editor_id:
        raise DraftsmithDBError(
            f"resolve_flag requires a real editor id (email); got {editor_id!r}"
        )
    async with get_db() as session:
        result = await session.execute(
            text(
                """
                UPDATE rigwire.draft_flags
                SET status = :action, resolved_by = :editor_id,
                    resolved_at = now(), resolution_note = :note
                WHERE id = :flag_id AND status = 'open'
                RETURNING *
                """
            ),
            {"flag_id": flag_id, "action": action, "editor_id": editor_id, "note": note},
        )
        row = result.mappings().first()
        await session.commit()
    if row is None:
        raise DraftsmithDBError(
            f"resolve_flag: no OPEN draft_flags row for id={flag_id} "
            "(already resolved, or id does not exist)"
        )
    return flag_from_row(row)


async def open_flag_count(job_id: str) -> int:
    async with get_db() as session:
        result = await session.execute(
            text(
                "SELECT count(*) AS n FROM rigwire.draft_flags "
                "WHERE job_id = :job_id AND status = 'open'"
            ),
            {"job_id": job_id},
        )
        row = result.mappings().first()
    return int(row["n"]) if row else 0
