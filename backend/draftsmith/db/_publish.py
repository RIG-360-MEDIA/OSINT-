"""backend.draftsmith.db._publish — rigwire.draft_publishes audit + job finalize."""
from __future__ import annotations

import json
from typing import Mapping

from sqlalchemy import text

from backend.database import get_db
from backend.draftsmith.db._common import DraftsmithDBError


async def record_publish(
    job_id: str,
    version_id: str,
    neon_story_id: str,
    editor_id: str,
    flags_summary: Mapping[str, int],
) -> None:
    """Box-side audit of the single Neon write, plus the job's terminal
    state transition — both in one transaction so a crash between the two
    can never leave the job non-terminal with an audit row already present
    (or vice versa). draft_publishes.job_id is UNIQUE: a second call for an
    already-published job raises DraftsmithDBError rather than silently
    double-publishing. The draft_jobs_publish_guard trigger independently
    enforces that published_by is a real editor id; this function ALSO
    requires the job to currently be in 'ready' state — the migration's
    CHECK constraint permits any state -> 'published' transition, so that
    workflow rule (only a fully-reviewed job may be published) is enforced
    here rather than in SQL."""
    if not editor_id or "@" not in editor_id:
        raise DraftsmithDBError(
            f"record_publish requires a real editor id (email); got {editor_id!r}"
        )
    async with get_db() as session:
        existing = await session.execute(
            text("SELECT 1 FROM rigwire.draft_publishes WHERE job_id = :job_id"),
            {"job_id": job_id},
        )
        if existing.first() is not None:
            raise DraftsmithDBError(f"record_publish: job_id={job_id} was already published")

        current = await session.execute(
            text("SELECT state FROM rigwire.draft_jobs WHERE id = :job_id"),
            {"job_id": job_id},
        )
        current_row = current.mappings().first()
        if current_row is None:
            raise DraftsmithDBError(f"record_publish: no draft_jobs row for id={job_id}")
        if current_row["state"] != "ready":
            raise DraftsmithDBError(
                f"record_publish: job_id={job_id} is in state "
                f"{current_row['state']!r}, not 'ready' — cannot publish"
            )

        await session.execute(
            text(
                """
                INSERT INTO rigwire.draft_publishes (
                    job_id, version_id, neon_story_id, editor_id, flags_summary
                ) VALUES (
                    :job_id, :version_id, :neon_story_id, :editor_id,
                    CAST(:flags_summary AS jsonb)
                )
                """
            ),
            {
                "job_id": job_id,
                "version_id": version_id,
                "neon_story_id": neon_story_id,
                "editor_id": editor_id,
                "flags_summary": json.dumps(dict(flags_summary)),
            },
        )
        result = await session.execute(
            text(
                """
                UPDATE rigwire.draft_jobs
                SET state = 'published', published_by = :editor_id,
                    published_story_id = :neon_story_id, published_at = now(),
                    updated_at = now()
                WHERE id = :job_id
                RETURNING id
                """
            ),
            {"job_id": job_id, "editor_id": editor_id, "neon_story_id": neon_story_id},
        )
        row = result.mappings().first()
        if row is None:
            raise DraftsmithDBError(f"record_publish: no draft_jobs row for id={job_id}")
        await session.commit()
