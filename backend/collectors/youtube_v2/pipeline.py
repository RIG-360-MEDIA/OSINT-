"""Hetzner-side orchestration: transcribed rows → extracted clips.

Reads rows the residential worker marked 'transcribed', runs Groq extraction +
embedding + storage, marks them 'extracted'. Groq keys stay server-side; this
never touches YouTube.

Also exposes the helpers the discovery side and the quality harness reuse, so
the demo runs the exact production code path.
"""
from __future__ import annotations

import json
import logging

from .extraction import extract_clips
from .metrics import PipelineMetrics
from .models import Transcript, TranscriptSegment, TranscriptSource
from .storage import build_stored_clips, persist_clips

logger = logging.getLogger("youtube_v2")

_DEFAULT_REGION = "telangana"

# Wholly-failed extractions (every Groq chunk 429'd / unparseable) are retried
# rather than burned to 'extracted'. After this many wholly-failed passes the
# row is marked 'failed' so a genuinely un-processable video can't loop forever.
EXTRACT_MAX_ATTEMPTS = 5


def transcript_from_json(video_id: str, data: dict) -> Transcript:
    """Reconstruct a Transcript from the worker's stored transcript_json."""
    return Transcript(
        video_id=video_id,
        language=str(data.get("language", "en")),
        source=TranscriptSource(data.get("source", TranscriptSource.AUTO_CAPTIONS.value)),
        segments=tuple(
            TranscriptSegment(
                start=float(s["start"]),
                duration=float(s.get("duration", 0.0)),
                text=str(s["text"]),
            )
            for s in data.get("segments", [])
            if s.get("text")
        ),
    )


async def load_entities(db) -> list[str]:
    """Canonical monitored entities sent to Groq.

    ``user_entities`` is the curated monitored list (~tens of rows) — the right
    set to look for and to canonicalize against. ``entity_dictionary`` is a
    19k-row, junk-laden validation table (see memory project_sentiment_redesign)
    and must NOT be used here: it would bloat the prompt and reintroduce noise.
    """
    from sqlalchemy import text

    rows = (
        await db.execute(
            text("SELECT canonical_name FROM user_entities ORDER BY canonical_name")
        )
    ).fetchall()
    return [r.canonical_name for r in rows if r.canonical_name]


async def load_alias_block(db, region: str = _DEFAULT_REGION) -> str:
    """Region-aware disambiguation block for the Groq prompt (best-effort)."""
    from sqlalchemy import text

    try:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT canonical_name, alias, COALESCE(notes,'') AS notes
                    FROM entity_aliases
                    WHERE region = :region OR region IS NULL
                    ORDER BY canonical_name, alias
                    """
                ),
                {"region": region},
            )
        ).fetchall()
    except Exception:  # noqa: BLE001 - table optional
        logger.warning("youtube_v2 alias load failed — empty block", exc_info=True)
        return ""

    if not rows:
        return ""
    grouped: dict[str, list[tuple[str, str]]] = {}
    for r in rows:
        grouped.setdefault(r.canonical_name, []).append((r.alias, r.notes))
    lines = ["ENTITY DISAMBIGUATION (use the EXACT canonical name):"]
    for canonical, items in grouped.items():
        aliases = " / ".join(f"'{a}'" for a, _ in items)
        note = next((n for _, n in items if n), "")
        lines.append(f"- {aliases} = {canonical}{f' — {note}' if note else ''}")
    return "\n".join(lines)


async def process_transcript(
    transcript: Transcript,
    *,
    video_title: str,
    channel_id: str,
    channel_name: str,
    published_at: str,
    entities: list[str],
    alias_block: str,
    db,
    persist: bool = True,
) -> tuple[list, PipelineMetrics]:
    """Run extraction → gating → embedding → (optional) persist for one video.

    Returns (stored_clips, metrics). With ``persist=False`` it builds clips and
    embeddings but writes nothing — used by the quality harness."""
    metrics = PipelineMetrics(video_id=transcript.video_id)

    clips = await extract_clips(
        transcript,
        video_title=video_title,
        channel_name=channel_name,
        entities=entities,
        metrics=metrics,
        alias_block=alias_block,
    )
    stored = build_stored_clips(
        clips,
        transcript,
        video_title=video_title,
        channel_id=channel_id,
        channel_name=channel_name,
        published_at=published_at,
        metrics=metrics,
    )
    if persist and stored:
        await persist_clips(stored, db, metrics)
    metrics.log_summary()
    return stored, metrics


async def run_extraction_batch(db, *, limit: int = 10) -> dict:
    """Process up to ``limit`` 'transcribed' rows into clips."""
    from sqlalchemy import text

    entities = await load_entities(db)
    alias_block = await load_alias_block(db)
    rows = (
        await db.execute(
            text(
                """
                SELECT video_id, video_title, channel_id, channel_name,
                       video_published_at, transcript_json, extract_attempts
                FROM pending_youtube_videos
                WHERE status='transcribed'
                ORDER BY transcribed_at
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
    ).fetchall()

    total_stored = 0
    retried = failed = 0
    for row in rows:
        data = row.transcript_json
        if isinstance(data, str):
            data = json.loads(data)
        transcript = transcript_from_json(row.video_id, data)
        stored, metrics = await process_transcript(
            transcript,
            video_title=row.video_title,
            channel_id=row.channel_id,
            channel_name=row.channel_name,
            published_at=str(row.video_published_at or ""),
            entities=entities,
            alias_block=alias_block,
            db=db,
            persist=True,
        )
        total_stored += len(stored)

        # Status decision — NEVER burn a video that wasn't really processed.
        # All Groq chunks failed (429 / parse) → the LLM never ran; leave the
        # row 'transcribed' so the beat retries it once the keys recover.
        # extract_attempts bounds the loop: give up to 'failed' after the cap.
        wholly_failed = metrics.chunks_ok == 0 and metrics.chunks_failed > 0
        if wholly_failed:
            attempts = (row.extract_attempts or 0) + 1
            if attempts >= EXTRACT_MAX_ATTEMPTS:
                await db.execute(
                    text(
                        "UPDATE pending_youtube_videos "
                        "SET status='failed', extract_attempts=:a, updated_at=now(), "
                        "last_error='extraction: all chunks failed after retries' "
                        "WHERE video_id=:vid"
                    ),
                    {"a": attempts, "vid": row.video_id},
                )
                failed += 1
            else:
                await db.execute(
                    text(
                        "UPDATE pending_youtube_videos "
                        "SET extract_attempts=:a, updated_at=now() "
                        "WHERE video_id=:vid"
                    ),
                    {"a": attempts, "vid": row.video_id},
                )
                retried += 1
            continue

        # The LLM ran (at least one chunk OK). Whether or not it found tracked
        # entities, the video is genuinely done — mark it extracted.
        await db.execute(
            text(
                "UPDATE pending_youtube_videos "
                "SET status='extracted', extracted_at=now(), updated_at=now() "
                "WHERE video_id=:vid"
            ),
            {"vid": row.video_id},
        )
    await db.commit()
    return {
        "processed": len(rows),
        "clips_stored": total_stored,
        "retried": retried,
        "failed": failed,
    }
