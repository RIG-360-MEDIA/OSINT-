"""backend.draftsmith.api._finalize — read-only helpers for /finalize + /published.

Three small direct reads that backend.draftsmith.db does not expose (it only
ever *mutates* draft_flags/draft_images with a return value, or gives a
job-wide open-flag *count* without a severity split): a red-severity open-flag
count, the currently-selected image (if any), and a whole-job flags summary.
All three reuse backend.database.get_db + the existing row->dataclass
serialisers in backend.draftsmith._db_serialize — no new writes, no new
tables, just SELECTs the frozen db package didn't need for its own callers.

If db/_flags.py or db/_images.py grows equivalent read helpers later, prefer
those over these local copies.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text

from backend.database import get_db
from backend.draftsmith._db_serialize import image_candidate_from_row
from backend.draftsmith.models import Draft, EvidenceItem, ImageCandidate


async def count_open_red_flags(job_id: str) -> int:
    async with get_db() as session:
        result = await session.execute(
            text(
                "SELECT count(*) AS n FROM rigwire.draft_flags "
                "WHERE job_id = :job_id AND status = 'open' AND severity = 'red'"
            ),
            {"job_id": job_id},
        )
        row = result.mappings().first()
    return int(row["n"]) if row else 0


async def selected_image(job_id: str) -> Optional[ImageCandidate]:
    async with get_db() as session:
        result = await session.execute(
            text(
                "SELECT * FROM rigwire.draft_images WHERE job_id = :job_id AND selected = true"
            ),
            {"job_id": job_id},
        )
        row = result.mappings().first()
    return image_candidate_from_row(row) if row else None


async def flags_summary(job_id: str) -> dict[str, int]:
    """{resolved, red, amber} snapshot across the whole job's flag history —
    matches PublishPayload.flags_summary / draft_publishes.flags_summary."""
    async with get_db() as session:
        result = await session.execute(
            text(
                """
                SELECT
                  count(*) FILTER (WHERE status <> 'open') AS resolved,
                  count(*) FILTER (WHERE severity = 'red')  AS red,
                  count(*) FILTER (WHERE severity = 'amber') AS amber
                FROM rigwire.draft_flags WHERE job_id = :job_id
                """
            ),
            {"job_id": job_id},
        )
        row = result.mappings().first()
    if row is None:
        return {"resolved": 0, "red": 0, "amber": 0}
    return {
        "resolved": int(row["resolved"]),
        "red": int(row["red"]),
        "amber": int(row["amber"]),
    }


async def render_body_markdown(job_id: str, draft: Draft) -> str:
    """Beats rendered "## subhead\\n\\ntext", plus a plain "## Sources" tail
    listing every cited source_id resolved back to its evidence snapshot —
    the exact shape PublishPayload.body_markdown promises."""
    from backend.draftsmith.db import select_evidence  # local import: avoid a cycle w/ db/__init__

    beat_md = "\n\n".join(f"## {b.subhead}\n\n{b.text}".strip() for b in draft.beats)

    ids: list[str] = []
    for beat in draft.beats:
        ids.extend(beat.source_ids)
    for fact in draft.key_facts:
        ids.extend(fact.source_ids)
    if draft.pull_quote and draft.pull_quote.source_id:
        ids.append(draft.pull_quote.source_id)
    unique_ids = sorted(set(ids))

    sources_md = "## Sources\n\n"
    if unique_ids:
        items: list[EvidenceItem] = await select_evidence(job_id, unique_ids)
        by_id = {item.source_id: item for item in items}
        lines: list[str] = []
        for source_id in unique_ids:
            item = by_id.get(source_id)
            if item is None:
                lines.append(f"- [{source_id}]")
                continue
            label = item.title or item.outlet or item.source_type
            lines.append(f"- {label} — {item.url}" if item.url else f"- {label}")
        sources_md += "\n".join(lines)
    else:
        sources_md += "_No cited sources._"

    return f"{beat_md}\n\n{sources_md}".strip()
