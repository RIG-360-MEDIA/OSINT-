"""backend.draftsmith.db._jobs — rigwire.draft_jobs CRUD (job spine + lease claim)."""
from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import text

from backend.database import get_db
from backend.draftsmith import config
from backend.draftsmith._db_serialize import to_json
from backend.draftsmith.db._common import DraftJob, DraftsmithDBError, job_from_row
from backend.draftsmith.models import Dials, JobState, QueryPlan


async def create_job(
    created_by: str, input_text: str, dials: Optional[Dials] = None,
) -> DraftJob:
    if not created_by or "@" not in created_by:
        raise DraftsmithDBError(
            f"create_job requires a real editor id (email); got {created_by!r}"
        )
    if not input_text or not input_text.strip():
        raise DraftsmithDBError("create_job requires non-empty input_text")
    resolved_dials = (dials or Dials()).clamp()
    async with get_db() as session:
        result = await session.execute(
            text(
                """
                INSERT INTO rigwire.draft_jobs (created_by, input_text, dials)
                VALUES (:created_by, :input_text, CAST(:dials AS jsonb))
                RETURNING *
                """
            ),
            {
                "created_by": created_by,
                "input_text": input_text,
                "dials": to_json(resolved_dials),
            },
        )
        row = result.mappings().first()
        await session.commit()
    if row is None:
        raise DraftsmithDBError("create_job: INSERT ... RETURNING produced no row")
    return job_from_row(row)


async def get_job(job_id: str) -> Optional[DraftJob]:
    async with get_db() as session:
        result = await session.execute(
            text("SELECT * FROM rigwire.draft_jobs WHERE id = :job_id"),
            {"job_id": job_id},
        )
        row = result.mappings().first()
    return job_from_row(row) if row else None


async def list_jobs(
    *, state: Optional[JobState] = None, created_by: Optional[str] = None,
    limit: int = 50, offset: int = 0,
) -> list[DraftJob]:
    if not (1 <= limit <= 500):
        raise DraftsmithDBError(f"list_jobs: limit must be 1-500, got {limit}")
    if offset < 0:
        raise DraftsmithDBError(f"list_jobs: offset must be >= 0, got {offset}")
    clauses: list[str] = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if state is not None:
        clauses.append("state = :state")
        params["state"] = state
    if created_by is not None:
        clauses.append("created_by = :created_by")
        params["created_by"] = created_by
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    async with get_db() as session:
        result = await session.execute(
            text(
                f"""
                SELECT * FROM rigwire.draft_jobs
                {where}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
        rows = result.mappings().all()
    return [job_from_row(r) for r in rows]


async def claim_next_job(
    *, lease_seconds: int = config.LEASE_SECONDS,
) -> Optional[DraftJob]:
    """Atomically claims either a fresh 'queued' job or a stuck job whose
    lease has expired (worker crash-recovery), and bumps it into 'planning'.
    FOR UPDATE SKIP LOCKED makes this safe under CONCURRENCY > 1 workers.
    Jobs already at config.MAX_ATTEMPTS are left alone — they need an
    operator/reaper to mark them 'failed', not another silent reclaim."""
    async with get_db() as session:
        result = await session.execute(
            text(
                """
                UPDATE rigwire.draft_jobs
                SET state = 'planning',
                    lease_until = now() + make_interval(secs => :lease_seconds),
                    attempt = attempt + 1,
                    updated_at = now()
                WHERE id = (
                    SELECT id FROM rigwire.draft_jobs
                    WHERE attempt < :max_attempts
                      AND (
                            state = 'queued'
                         OR (
                              state NOT IN ('ready', 'failed', 'cancelled', 'published')
                              AND lease_until IS NOT NULL
                              AND lease_until < now()
                            )
                          )
                    ORDER BY created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING *
                """
            ),
            {"lease_seconds": lease_seconds, "max_attempts": config.MAX_ATTEMPTS},
        )
        row = result.mappings().first()
        await session.commit()
    return job_from_row(row) if row else None


_JOB_PATCHABLE_COLUMNS = frozenset({
    "error", "stage_progress", "attempt", "lease_until",
    "published_by", "published_story_id", "published_at",
})


async def update_job_state(job_id: str, state: JobState, **patch: Any) -> DraftJob:
    unknown = set(patch) - _JOB_PATCHABLE_COLUMNS
    if unknown:
        raise DraftsmithDBError(
            f"update_job_state: unsupported patch field(s) {sorted(unknown)}; "
            f"allowed: {sorted(_JOB_PATCHABLE_COLUMNS)}"
        )
    set_clauses = ["state = :state", "updated_at = now()"]
    params: dict[str, Any] = {"job_id": job_id, "state": state}
    for field, value in patch.items():
        if field == "stage_progress":
            set_clauses.append(f"{field} = CAST(:{field} AS jsonb)")
            params[field] = json.dumps(value)
        else:
            set_clauses.append(f"{field} = :{field}")
            params[field] = value
    async with get_db() as session:
        result = await session.execute(
            text(
                f"""
                UPDATE rigwire.draft_jobs
                SET {', '.join(set_clauses)}
                WHERE id = :job_id
                RETURNING *
                """
            ),
            params,
        )
        row = result.mappings().first()
        await session.commit()
    if row is None:
        raise DraftsmithDBError(f"update_job_state: no draft_jobs row for id={job_id}")
    return job_from_row(row)


async def save_query_plan(job_id: str, plan: QueryPlan) -> DraftJob:
    async with get_db() as session:
        result = await session.execute(
            text(
                """
                UPDATE rigwire.draft_jobs
                SET query_plan = CAST(:plan AS jsonb), updated_at = now()
                WHERE id = :job_id
                RETURNING *
                """
            ),
            {"job_id": job_id, "plan": to_json(plan)},
        )
        row = result.mappings().first()
        await session.commit()
    if row is None:
        raise DraftsmithDBError(f"save_query_plan: no draft_jobs row for id={job_id}")
    return job_from_row(row)
