"""backend.draftsmith.db._common — shared error type + local row shapes.

models.py has no "Job" dataclass (draft_jobs is box-internal state machinery,
not part of the CMS-facing frozen contract) — DraftJob and StoredVersion here
are LOCAL to the DB layer, not the frozen contract in models.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional

from backend.draftsmith._db_serialize import (
    dials_from_row,
    load_maybe_json,
    query_plan_from_json,
)
from backend.draftsmith.models import Dials, DraftVersion, JobState, QueryPlan


class DraftsmithDBError(Exception):
    """Raised on any draft_* DB operation that cannot be satisfied: a
    missing row where the caller expected one, an invalid state/action
    argument, a re-publish attempt, etc. Never swallowed."""


@dataclass(frozen=True)
class DraftJob:
    """rigwire.draft_jobs row."""

    id: str
    created_by: str
    input_text: str
    dials: Dials
    state: JobState
    stage_progress: Mapping[str, Any]
    query_plan: Optional[QueryPlan]
    error: Optional[str]
    attempt: int
    lease_until: Optional[datetime]
    published_by: Optional[str]
    published_story_id: Optional[str]
    published_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class StoredVersion:
    """A persisted DraftVersion plus its DB id. draft_flags.version_id needs
    this id and the frozen DraftVersion dataclass carries none."""

    id: str
    job_id: str
    version: DraftVersion


def job_from_row(row: Mapping[str, Any]) -> DraftJob:
    return DraftJob(
        id=str(row["id"]),
        created_by=row["created_by"],
        input_text=row["input_text"],
        dials=dials_from_row(load_maybe_json(row["dials"])),
        state=row["state"],
        stage_progress=load_maybe_json(row["stage_progress"]) or {},
        query_plan=query_plan_from_json(load_maybe_json(row["query_plan"])),
        error=row.get("error"),
        attempt=row["attempt"],
        lease_until=row.get("lease_until"),
        published_by=row.get("published_by"),
        published_story_id=row.get("published_story_id"),
        published_at=row.get("published_at"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
