"""
Smoke test: YouTube clip substrate enrichment (Phase G verify).

Inserts one synthetic clip → runs enrich inline → asserts child tables
populated + content_items shows the row + matview resolves → cleans up.

Usage (inside rig-backend container):
    python -m scripts.smoke_youtube_clip_enrich
"""
from __future__ import annotations

import asyncio
import sys


# ── Synthetic clip ────────────────────────────────────────────────────────────
# Short political transcript mentioning a known entity.
_VIDEO_ID = "SMOKE_TEST_VIDEO_001"
_ENTITY   = "Revanth Reddy"
_SEGMENT  = (
    "[0s] Today we will discuss the latest announcements from the government. "
    "[5s] Chief Minister Revanth Reddy addressed a press conference in Hyderabad. "
    "[12s] He announced a new welfare scheme for farmers across Telangana. "
    "[20s] The scheme will provide direct financial support to over two million farmers. "
    "[30s] Opposition leader KCR criticised the announcement calling it insufficient. "
    "[38s] Revanth Reddy responded that his government has delivered on all election promises. "
    "[48s] The press conference ended with questions from reporters."
)


async def _run_smoke() -> None:
    from sqlalchemy import text
    from backend.database import get_db

    print("=== YouTube clip enrichment smoke test ===")

    # ── 1. Insert synthetic clip ──────────────────────────────────────────────
    print("\n[1] Inserting synthetic clip...")
    async with get_db() as db:
        # Clean up any leftover from a previous run first.
        await db.execute(
            text("DELETE FROM youtube_clips_v2 WHERE video_id = :v"),
            {"v": _VIDEO_ID},
        )
        await db.commit()

        row = (
            await db.execute(
                text(
                    """
                    INSERT INTO youtube_clips_v2 (
                        video_id, video_title, channel_id, channel_name,
                        video_url, clip_start_seconds, clip_end_seconds, embed_url,
                        matched_entity, summary, transcript_segment,
                        transcript_language, transcript_source,
                        confidence, importance, substrate_status
                    ) VALUES (
                        :vid, :title, 'UC_SMOKE', 'Smoke Test Channel',
                        'https://youtube.com/watch?v=' || :vid,
                        0, 55,
                        'https://youtube.com/embed/' || :vid || '?t=0',
                        :entity,
                        'Revanth Reddy announced a new welfare scheme for Telangana farmers.',
                        :seg, 'en', 'auto_captions',
                        0.9, 'high', 'pending'
                    )
                    RETURNING id, clip_uuid
                    """
                ),
                {"vid": _VIDEO_ID, "title": "Smoke Test: CM Press Conference",
                 "entity": _ENTITY, "seg": _SEGMENT},
            )
        ).fetchone()
        await db.commit()

    clip_id  = int(row.id)
    clip_uuid = str(row.clip_uuid)
    print(f"    clip_id={clip_id}  clip_uuid={clip_uuid}")

    # ── 2. Run enrichment inline ──────────────────────────────────────────────
    print("\n[2] Running enrich_clip inline (real LLM call)...")
    from backend.tasks.youtube_clip_enrich import _enrich_one_by_id
    result = await _enrich_one_by_id(clip_id)
    print(f"    result={result}")
    if result.get("status") not in ("ok", "skipped"):
        print("FAIL — enrich returned non-ok status")
        await _cleanup(clip_id)
        sys.exit(1)

    # ── 3. Assert substrate_status='ok' ──────────────────────────────────────
    print("\n[3] Checking substrate_status...")
    async with get_db() as db:
        row2 = (
            await db.execute(
                text(
                    "SELECT substrate_status, extraction_version, enriched_at, "
                    "       topic_fine, topic_category, segment_type "
                    "FROM youtube_clips_v2 WHERE id = :id"
                ),
                {"id": clip_id},
            )
        ).fetchone()
    print(f"    status={row2.substrate_status}  ev={row2.extraction_version}"
          f"  topic={row2.topic_fine}/{row2.topic_category}"
          f"  segment_type={row2.segment_type}  enriched_at={row2.enriched_at}")
    assert row2.substrate_status == "ok", f"Expected ok, got {row2.substrate_status}"
    assert row2.extraction_version == 3, f"Expected ev=3, got {row2.extraction_version}"
    assert row2.enriched_at is not None, "enriched_at is null"
    print("    PASS")

    # ── 4. Assert child tables ────────────────────────────────────────────────
    print("\n[4] Checking child tables...")
    async with get_db() as db:
        n_claims = (await db.execute(
            text("SELECT COUNT(*) FROM youtube_clip_claims WHERE clip_id=:id"),
            {"id": clip_id},
        )).scalar()
        n_quotes = (await db.execute(
            text("SELECT COUNT(*) FROM youtube_clip_quotes WHERE clip_id=:id"),
            {"id": clip_id},
        )).scalar()
        n_stances = (await db.execute(
            text("SELECT COUNT(*) FROM youtube_clip_stances WHERE clip_id=:id"),
            {"id": clip_id},
        )).scalar()
        n_locs = (await db.execute(
            text("SELECT COUNT(*) FROM youtube_clip_locations WHERE clip_id=:id"),
            {"id": clip_id},
        )).scalar()
    print(f"    claims={n_claims}  quotes={n_quotes}  stances={n_stances}  locations={n_locs}")
    total_child = n_claims + n_quotes + n_stances + n_locs
    assert total_child > 0, "No child rows written — enrichment produced nothing"
    print("    PASS")

    # ── 5. Assert content_items shows the clip ────────────────────────────────
    print("\n[5] Checking content_items union view...")
    async with get_db() as db:
        ci = (
            await db.execute(
                text(
                    "SELECT src, headline, language, primary_subject "
                    "FROM content_items WHERE id = :uuid"
                ),
                {"uuid": clip_uuid},
            )
        ).fetchone()
    assert ci is not None, "Clip not found in content_items"
    assert ci.src == "clip", f"Expected src=clip, got {ci.src}"
    print(f"    src={ci.src}  headline={ci.headline[:50]!r}"
          f"  lang={ci.language}  subject={ci.primary_subject!r}")
    print("    PASS")

    # ── 6. Matview refresh + entity resolution ────────────────────────────────
    print("\n[6] Refreshing youtube_clip_entity_mentions matview...")
    async with get_db() as db:
        await db.execute(
            text("REFRESH MATERIALIZED VIEW CONCURRENTLY youtube_clip_entity_mentions")
        )
        n_mentions = (
            await db.execute(
                text(
                    "SELECT COUNT(*) FROM youtube_clip_entity_mentions WHERE clip_id=:id"
                ),
                {"id": clip_id},
            )
        ).scalar()
        await db.commit()
    print(f"    entity_mention rows for this clip: {n_mentions}")
    if n_mentions == 0:
        print("    WARN — entity not in entity_lookup (matview empty for this clip)."
              " OK if Revanth Reddy is not yet in entity_dictionary.")
    else:
        print("    PASS")

    # ── 7. Cleanup ────────────────────────────────────────────────────────────
    await _cleanup(clip_id)
    print("\n=== SMOKE TEST PASSED ===")


async def _cleanup(clip_id: int) -> None:
    from sqlalchemy import text
    from backend.database import get_db

    print("\n[cleanup] Removing synthetic rows...")
    async with get_db() as db:
        await db.execute(
            text("DELETE FROM youtube_clips_v2 WHERE id = :id"), {"id": clip_id}
        )
        await db.commit()
    print("    done.")


if __name__ == "__main__":
    asyncio.run(_run_smoke())
