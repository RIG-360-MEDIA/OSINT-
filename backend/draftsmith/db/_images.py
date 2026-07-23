"""backend.draftsmith.db._images — rigwire.draft_images CRUD (6-slot thumbnail candidates)."""
from __future__ import annotations

from typing import Sequence

from sqlalchemy import text

from backend.database import get_db
from backend.draftsmith._db_serialize import image_candidate_from_row
from backend.draftsmith.db._common import DraftsmithDBError
from backend.draftsmith.models import ImageCandidate


async def save_images(job_id: str, images: Sequence[ImageCandidate]) -> list[ImageCandidate]:
    """Upserts on (job_id, slot). Every re-save resets that slot's
    `selected` to false — select_image is the only writer of selected=true."""
    if not images:
        return []
    stored: list[ImageCandidate] = []
    async with get_db() as session:
        for image in images:
            result = await session.execute(
                text(
                    """
                    INSERT INTO rigwire.draft_images (
                        job_id, slot, origin, url, thumb_url, license, license_url,
                        attribution, needs_license_review
                    ) VALUES (
                        :job_id, :slot, :origin, :url, :thumb_url, :license, :license_url,
                        :attribution, :needs_license_review
                    )
                    ON CONFLICT (job_id, slot) DO UPDATE SET
                        origin = EXCLUDED.origin,
                        url = EXCLUDED.url,
                        thumb_url = EXCLUDED.thumb_url,
                        license = EXCLUDED.license,
                        license_url = EXCLUDED.license_url,
                        attribution = EXCLUDED.attribution,
                        needs_license_review = EXCLUDED.needs_license_review,
                        selected = false
                    RETURNING *
                    """
                ),
                {
                    "job_id": job_id,
                    "slot": image.slot,
                    "origin": image.origin,
                    "url": image.url,
                    "thumb_url": image.thumb_url,
                    "license": image.license,
                    "license_url": image.license_url,
                    "attribution": image.attribution,
                    # always true for origin='web' per the frozen contract, even
                    # if the caller forgot to set it.
                    "needs_license_review": image.needs_license_review or image.origin == "web",
                },
            )
            row = result.mappings().first()
            if row is not None:
                stored.append(image_candidate_from_row(row))
        await session.commit()
    return stored


async def select_image(job_id: str, slot: int) -> ImageCandidate:
    """Marks exactly one slot selected=true for the job (single hero image
    per PublishPayload.image_url); every other slot for the job is flipped
    to selected=false first."""
    async with get_db() as session:
        await session.execute(
            text("UPDATE rigwire.draft_images SET selected = false WHERE job_id = :job_id"),
            {"job_id": job_id},
        )
        result = await session.execute(
            text(
                """
                UPDATE rigwire.draft_images
                SET selected = true
                WHERE job_id = :job_id AND slot = :slot
                RETURNING *
                """
            ),
            {"job_id": job_id, "slot": slot},
        )
        row = result.mappings().first()
        await session.commit()
    if row is None:
        raise DraftsmithDBError(
            f"select_image: no draft_images row for job_id={job_id} slot={slot}"
        )
    return image_candidate_from_row(row)
