"""backend.draftsmith.db — async CRUD for rigwire.draft_* (migrations/001_draftsmith.sql).

Reuses backend.database.get_db (SQLAlchemy async session + `text()`) — the
same engine/session factory every other pipeline module uses. This package
performs the ONLY writes draftsmith does on the box; Neon is touched solely
via record_publish's audit row (the actual Neon write happens in the API/CMS
layer, not here).

Split into one small module per draft_* table (kept under the file-size
budget) and re-exported here so callers only ever need:

    from backend.draftsmith import db
    job = await db.create_job(...)

Row -> models.py dataclass mapping lives in backend.draftsmith._db_serialize;
every module here issues parameterised SQL (every value bound, never
string-formatted) and shapes results via that shared helper.

models.py has no "Job" dataclass (draft_jobs predates the frozen contract
freeze and isn't part of the CMS-facing shape) — DraftJob and StoredVersion
(see db._common) are LOCAL to this DB layer, not the frozen contract.
"""
from __future__ import annotations

from backend.draftsmith.db._common import DraftJob, DraftsmithDBError, StoredVersion
from backend.draftsmith.db._evidence import save_evidence, select_evidence
from backend.draftsmith.db._flags import create_flags, open_flag_count, resolve_flag
from backend.draftsmith.db._images import save_images, select_image
from backend.draftsmith.db._jobs import (
    claim_next_job,
    create_job,
    get_job,
    list_jobs,
    save_query_plan,
    update_job_state,
)
from backend.draftsmith.db._publish import record_publish
from backend.draftsmith.db._versions import latest_version, save_version

__all__ = [
    "DraftJob",
    "DraftsmithDBError",
    "StoredVersion",
    "create_job",
    "get_job",
    "list_jobs",
    "claim_next_job",
    "update_job_state",
    "save_query_plan",
    "save_evidence",
    "select_evidence",
    "save_version",
    "latest_version",
    "create_flags",
    "resolve_flag",
    "open_flag_count",
    "save_images",
    "select_image",
    "record_publish",
]
