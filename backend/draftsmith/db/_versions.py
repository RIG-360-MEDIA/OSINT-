"""backend.draftsmith.db._versions — rigwire.draft_versions CRUD (draft/repair/editor history)."""
from __future__ import annotations

import dataclasses
import json
from typing import Optional

from sqlalchemy import text

from backend.database import get_db
from backend.draftsmith._db_serialize import draft_version_from_row
from backend.draftsmith.db._common import DraftsmithDBError, StoredVersion
from backend.draftsmith.models import DraftVersion


async def save_version(job_id: str, version: DraftVersion) -> StoredVersion:
    draft = version.draft
    async with get_db() as session:
        result = await session.execute(
            text(
                """
                INSERT INTO rigwire.draft_versions (
                    job_id, version, kind, headline, dek, beats, key_facts,
                    pull_quote, unsourced_gaps, word_count, verify_report, created_by
                ) VALUES (
                    :job_id, :version, :kind, :headline, :dek, CAST(:beats AS jsonb),
                    CAST(:key_facts AS jsonb), CAST(:pull_quote AS jsonb),
                    CAST(:unsourced_gaps AS jsonb), :word_count,
                    CAST(:verify_report AS jsonb), :created_by
                )
                ON CONFLICT (job_id, version) DO UPDATE SET
                    kind = EXCLUDED.kind,
                    headline = EXCLUDED.headline,
                    dek = EXCLUDED.dek,
                    beats = EXCLUDED.beats,
                    key_facts = EXCLUDED.key_facts,
                    pull_quote = EXCLUDED.pull_quote,
                    unsourced_gaps = EXCLUDED.unsourced_gaps,
                    word_count = EXCLUDED.word_count,
                    verify_report = EXCLUDED.verify_report,
                    created_by = EXCLUDED.created_by
                RETURNING *
                """
            ),
            {
                "job_id": job_id,
                "version": version.version,
                "kind": version.kind,
                "headline": draft.headline,
                "dek": draft.dek,
                "beats": json.dumps([dataclasses.asdict(b) for b in draft.beats]),
                "key_facts": json.dumps([dataclasses.asdict(k) for k in draft.key_facts]),
                "pull_quote": (
                    json.dumps(dataclasses.asdict(draft.pull_quote))
                    if draft.pull_quote else "null"
                ),
                "unsourced_gaps": json.dumps(list(draft.unsourced_gaps)),
                "word_count": draft.word_count,
                "verify_report": (
                    json.dumps(dataclasses.asdict(version.verify_report))
                    if version.verify_report else "null"
                ),
                "created_by": version.created_by,
            },
        )
        row = result.mappings().first()
        await session.commit()
    if row is None:
        raise DraftsmithDBError(
            f"save_version: INSERT ... RETURNING produced no row for job_id={job_id}"
        )
    return StoredVersion(id=str(row["id"]), job_id=job_id, version=draft_version_from_row(row))


async def latest_version(job_id: str) -> Optional[StoredVersion]:
    async with get_db() as session:
        result = await session.execute(
            text(
                """
                SELECT * FROM rigwire.draft_versions
                WHERE job_id = :job_id
                ORDER BY version DESC
                LIMIT 1
                """
            ),
            {"job_id": job_id},
        )
        row = result.mappings().first()
    if row is None:
        return None
    return StoredVersion(id=str(row["id"]), job_id=job_id, version=draft_version_from_row(row))
