"""backend.draftsmith.db._evidence — rigwire.draft_evidence CRUD (gather + rank stages)."""
from __future__ import annotations

import json
from typing import Any, Optional, Sequence

from sqlalchemy import text

from backend.database import get_db
from backend.draftsmith._db_serialize import evidence_item_from_row
from backend.draftsmith.db._common import DraftsmithDBError
from backend.draftsmith.models import EvidenceItem


async def save_evidence(job_id: str, items: Sequence[EvidenceItem]) -> list[EvidenceItem]:
    """Frozen-snapshot insert of gathered evidence. Upserts on (job_id,
    source_id) so re-running the gather stage never duplicates a citation
    handle. `selected` is untouched by this function — the rank stage is the
    only writer of selected=true (see select_evidence)."""
    if not items:
        return []
    stored: list[EvidenceItem] = []
    async with get_db() as session:
        for item in items:
            result = await session.execute(
                text(
                    """
                    INSERT INTO rigwire.draft_evidence (
                        job_id, source_id, source_type, trust_tier, title, url,
                        outlet, author, published_at, text_snapshot, raw, relevance
                    ) VALUES (
                        :job_id, :source_id, :source_type, :trust_tier, :title, :url,
                        :outlet, :author, :published_at, :text_snapshot,
                        CAST(:raw AS jsonb), :relevance
                    )
                    ON CONFLICT (job_id, source_id) DO UPDATE SET
                        source_type = EXCLUDED.source_type,
                        trust_tier = EXCLUDED.trust_tier,
                        title = EXCLUDED.title,
                        url = EXCLUDED.url,
                        outlet = EXCLUDED.outlet,
                        author = EXCLUDED.author,
                        published_at = EXCLUDED.published_at,
                        text_snapshot = EXCLUDED.text_snapshot,
                        raw = EXCLUDED.raw,
                        relevance = EXCLUDED.relevance
                    RETURNING *
                    """
                ),
                {
                    "job_id": job_id,
                    "source_id": item.source_id,
                    "source_type": item.source_type,
                    "trust_tier": item.trust_tier,
                    "title": item.title,
                    "url": item.url,
                    "outlet": item.outlet,
                    "author": item.author,
                    "published_at": item.published_at,
                    "text_snapshot": item.text,
                    "raw": json.dumps(dict(item.extra)),
                    "relevance": item.relevance,
                },
            )
            row = result.mappings().first()
            if row is not None:
                stored.append(evidence_item_from_row(row))
        await session.commit()
    return stored


async def select_evidence(
    job_id: str,
    source_ids: Optional[Sequence[str]] = None,
    *,
    mark_selected: bool = False,
) -> list[EvidenceItem]:
    """Dual-purpose per the shared-clients interface: the rank stage's
    WRITE path and every stage's READ path.

    mark_selected=True: flips selected=true for exactly the given
    source_ids (the rank stage's picks for the BRIEF); every other row for
    this job is flipped to selected=false first, so re-ranking a job is
    idempotent. Returns the newly-selected items. source_ids is required.

    mark_selected=False (default): read-only. Returns evidence for the job,
    filtered to source_ids when given, else every row, ordered by relevance
    descending (NULLs last).
    """
    if mark_selected:
        if not source_ids:
            raise DraftsmithDBError(
                "select_evidence(mark_selected=True) requires a non-empty source_ids"
            )
        async with get_db() as session:
            await session.execute(
                text(
                    "UPDATE rigwire.draft_evidence SET selected = false WHERE job_id = :job_id"
                ),
                {"job_id": job_id},
            )
            result = await session.execute(
                text(
                    """
                    UPDATE rigwire.draft_evidence
                    SET selected = true
                    WHERE job_id = :job_id AND source_id = ANY(:source_ids)
                    RETURNING *
                    """
                ),
                {"job_id": job_id, "source_ids": list(source_ids)},
            )
            rows = result.mappings().all()
            await session.commit()
        return [evidence_item_from_row(r) for r in rows]

    clauses = ["job_id = :job_id"]
    params: dict[str, Any] = {"job_id": job_id}
    if source_ids:
        clauses.append("source_id = ANY(:source_ids)")
        params["source_ids"] = list(source_ids)
    async with get_db() as session:
        result = await session.execute(
            text(
                f"""
                SELECT * FROM rigwire.draft_evidence
                WHERE {' AND '.join(clauses)}
                ORDER BY relevance DESC NULLS LAST
                """
            ),
            params,
        )
        rows = result.mappings().all()
    return [evidence_item_from_row(r) for r in rows]
