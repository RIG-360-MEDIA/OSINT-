"""Build + persist StoredClips: embeddings, dedup, invariants.

Final gate before the database. Enforces:
  - real timestamps (validate_timestamps) — rejects fake 0/15 windows;
  - non-empty transcript_segment (the real caption text in the window) — the
    old pipeline stored '' on 8/12 sampled clips;
  - timestamp ↔ URL invariant — embed_url always carries the start offset
    (?start=<s>), and we only ever store real-timestamp clips, so the two
    never disagree;
  - within-video dedup (same entity within DEDUP_SECONDS);
  - English embedding generated from the summary (LaBSE 768-d).

Inserts are idempotent via UNIQUE(video_id, clip_start_seconds, matched_entity).
"""
from __future__ import annotations

import logging
from datetime import datetime

from .metrics import PipelineMetrics
from .models import (
    ExtractedClip,
    Importance,
    SOURCE_CONFIDENCE,
    StoredClip,
    Transcript,
)
from .quality import RejectReason, is_empty_text, validate_timestamps

logger = logging.getLogger("youtube_v2")

_DEDUP_SECONDS = 5
_LEAD_IN = 5          # seconds of context before the mention
_MIN_WINDOW = 15
_MAX_WINDOW = 120

# Per-clip confidence = source-reliability × the LLM's own importance signal,
# so the stored score reflects BOTH how trustworthy the transcript source is
# AND how salient the model judged the mention — instead of a flat constant
# (every clip was previously 0.85 because all transcripts are auto_captions).
_IMPORTANCE_CONF_WEIGHT: dict[Importance, float] = {
    Importance.HIGH: 1.0,
    Importance.MEDIUM: 0.88,
    Importance.LOW: 0.70,
}


def _window_text(transcript: Transcript, start: int, end: int) -> str:
    """The real caption text spanning [start-lead, end]. Never fabricated."""
    lo = max(0, start - _LEAD_IN)
    parts = [
        seg.text.strip()
        for seg in transcript.segments
        if seg.start >= lo and seg.start <= end + 1
    ]
    return " ".join(p for p in parts if p).strip()


def _clamp_window(start: int, end: int) -> tuple[int, int]:
    """Enforce a sane clip length around the mention."""
    start = max(0, start - _LEAD_IN)
    span = end - start
    if span < _MIN_WINDOW:
        end = start + _MIN_WINDOW
    elif span > _MAX_WINDOW:
        end = start + _MAX_WINDOW
    return start, end


def build_stored_clips(
    clips: list[ExtractedClip],
    transcript: Transcript,
    *,
    video_title: str,
    channel_id: str,
    channel_name: str,
    published_at: str,
    metrics: PipelineMetrics,
) -> list[StoredClip]:
    """Apply the final gates and attach embeddings. Pure except for the LaBSE
    call; returns the clips that survive."""
    from backend.nlp.nlp_embedding import generate_embedding

    duration = transcript.duration_seconds
    source_conf = SOURCE_CONFIDENCE[transcript.source]
    seen: list[tuple[str, int]] = []
    out: list[StoredClip] = []

    for clip in clips:
        if not validate_timestamps(clip.start_seconds, clip.end_seconds, duration):
            metrics.record_reject(
                RejectReason.BAD_TIMESTAMP,
                f"start={clip.start_seconds} end={clip.end_seconds}",
            )
            continue

        # within-video dedup: same entity within DEDUP_SECONDS of a kept clip
        if any(
            e == clip.entity and abs(s - clip.start_seconds) <= _DEDUP_SECONDS
            for e, s in seen
        ):
            metrics.record_reject(RejectReason.DUPLICATE, clip.entity)
            continue

        start, end = _clamp_window(clip.start_seconds, clip.end_seconds)
        segment = _window_text(transcript, clip.start_seconds, end)
        if is_empty_text(segment):
            metrics.record_reject(RejectReason.EMPTY_SEGMENT, clip.entity)
            continue

        embedding = generate_embedding(clip.summary)
        if embedding is None:
            # summary too short for LaBSE — that is itself a quality signal
            metrics.record_reject(RejectReason.FILLER_SUMMARY, "embed_none")
            continue

        seen.append((clip.entity, clip.start_seconds))
        out.append(
            StoredClip(
                video_id=transcript.video_id,
                video_title=video_title,
                channel_id=channel_id,
                channel_name=channel_name,
                video_published_at=published_at,
                matched_entity=clip.entity,
                clip_start_seconds=start,
                clip_end_seconds=end,
                summary=clip.summary,
                transcript_segment=segment,
                transcript_language=transcript.language,
                transcript_source=transcript.source,
                confidence=round(
                    source_conf * _IMPORTANCE_CONF_WEIGHT.get(clip.importance, 0.88), 3
                ),
                embedding=tuple(embedding),
                importance=clip.importance,
            )
        )
    return out


def _coerce_dt(value) -> datetime | None:
    """Coerce a published-at value to a tz-aware datetime for the TIMESTAMPTZ
    column. The extraction path stringifies it (str(row.video_published_at)),
    but asyncpg refuses a str for timestamptz — so parse it back, or NULL."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


async def persist_clips(clips: list[StoredClip], db, metrics: PipelineMetrics) -> int:
    """Insert clips into youtube_clips_v2. Idempotent on the unique key."""
    from sqlalchemy import text

    if not clips:
        return 0

    stored = 0
    for c in clips:
        try:
            await db.execute(
                text(
                    """
                    INSERT INTO youtube_clips_v2 (
                        video_id, video_title, channel_id, channel_name,
                        video_published_at, video_url,
                        clip_start_seconds, clip_end_seconds, embed_url,
                        matched_entity, summary, transcript_segment,
                        transcript_language, transcript_source, confidence,
                        importance, labse_embedding
                    ) VALUES (
                        :video_id, :video_title, :channel_id, :channel_name,
                        :video_published_at, :video_url,
                        :clip_start_seconds, :clip_end_seconds, :embed_url,
                        :matched_entity, :summary, :transcript_segment,
                        :transcript_language, :transcript_source, :confidence,
                        :importance, CAST(:embedding AS vector)
                    )
                    ON CONFLICT (video_id, clip_start_seconds, matched_entity)
                    DO NOTHING
                    """
                ),
                {
                    "video_id": c.video_id,
                    "video_title": c.video_title,
                    "channel_id": c.channel_id,
                    "channel_name": c.channel_name,
                    "video_published_at": _coerce_dt(c.video_published_at),
                    "video_url": f"https://www.youtube.com/watch?v={c.video_id}",
                    "clip_start_seconds": c.clip_start_seconds,
                    "clip_end_seconds": c.clip_end_seconds,
                    "embed_url": c.embed_url,
                    "matched_entity": c.matched_entity,
                    "summary": c.summary,
                    "transcript_segment": c.transcript_segment,
                    "transcript_language": c.transcript_language,
                    "transcript_source": c.transcript_source.value,
                    "confidence": c.confidence,
                    "importance": c.importance.value,
                    # pgvector needs a string literal + an explicit CAST; asyncpg
                    # cannot encode a raw Python list to the vector type. Mirrors
                    # backend/nlp/nlp_embedding.py (the proven article path).
                    "embedding": str(list(c.embedding)),
                },
            )
            stored += 1
        except Exception:  # noqa: BLE001
            logger.warning(
                "youtube_v2 insert failed video=%s entity=%s",
                c.video_id, c.matched_entity, exc_info=True,
            )
    metrics.record_stored(stored)
    return stored
