"""Append-only audit log writer for dossier actions.

Every mutating action (run, refresh, sensitive-source invocation) writes one
row. Never updated or deleted in normal operation.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text

from backend.database import get_db

log = logging.getLogger(__name__)


async def record(
    *,
    user_id: str,
    action: str,
    dossier_id: UUID | None = None,
    target: str | None = None,
    purpose_note: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        async with get_db() as db:
            await db.execute(
                text(
                    """
                    INSERT INTO dossier_audit_log
                        (user_id, dossier_id, action, target, purpose_note, metadata)
                    VALUES
                        (:user_id, :dossier_id, :action, :target, :purpose_note, :metadata)
                    """
                ),
                {
                    "user_id": user_id,
                    "dossier_id": str(dossier_id) if dossier_id else None,
                    "action": action,
                    "target": target,
                    "purpose_note": purpose_note,
                    "metadata": json.dumps(metadata) if metadata else None,
                },
            )
            await db.commit()
    except Exception as e:
        # Audit failure must never break the user-facing flow.
        log.warning("dossier audit write failed: %s", e)
