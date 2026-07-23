"""backend.draftsmith.api._brief — reconstruct the BRIEF text for a job.

The BRIEF the writer/verifier consumed (prompts.build_draft_prompt /
build_verify_prompt's `brief: str`) is never persisted verbatim — there is no
column for it in migrations/001_draftsmith.sql, and models.py has no shape
for it. worker.py holds it only in memory for the duration of one run_job()
call (via stages.build_brief). When an editor later re-triggers /verify on a
saved draft (potentially after their own manual edit), we need that same
text again.

Reconstructed here from what IS persisted: the job's frozen QueryPlan plus
its selected draft_evidence rows, fed through the SAME stages.build_brief
the worker uses — so this is a faithful replay of the real format, not a
hand-rolled duplicate of it. The one difference from the original run: rank
already trimmed/truncated the evidence before handing it to build_brief, and
that trimming is not persisted (models.EvidenceItem carries no `selected`
flag or post-rank text-cap state) — so this replay runs build_brief over the
full-length selected snapshots, which can be a superset of what the writer
originally saw (never a subset of the citation handles).
"""
from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import text

from backend.database import get_db
from backend.draftsmith._db_serialize import evidence_item_from_row
from backend.draftsmith.models import EvidenceItem, QueryPlan
from backend.draftsmith.stages import build_brief


async def selected_evidence(job_id: str) -> list[EvidenceItem]:
    """Read-only fetch of the evidence rows the rank stage marked selected
    (i.e. the ones that made it into the BRIEF). models.EvidenceItem carries
    no `selected` flag, so this filters on the raw draft_evidence column
    directly rather than going through db.select_evidence's read path."""
    async with get_db() as session:
        result = await session.execute(
            text(
                """
                SELECT * FROM rigwire.draft_evidence
                WHERE job_id = :job_id AND selected = true
                ORDER BY relevance DESC NULLS LAST
                """
            ),
            {"job_id": job_id},
        )
        rows = result.mappings().all()
    return [evidence_item_from_row(r) for r in rows]


def rebuild_brief(query_plan: Optional[QueryPlan], evidence: Sequence[EvidenceItem]) -> str:
    """Replay stages.build_brief over the persisted selection. Returns ""
    when there's no query_plan to anchor the BRIEF (build_brief requires one);
    an empty `evidence` list is not special-cased — build_brief handles it
    (anchor + directives, no evidence sections)."""
    if query_plan is None:
        return ""
    return build_brief(list(evidence), query_plan).text
