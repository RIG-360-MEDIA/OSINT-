"""Immutable data model for the youtube_v2 pipeline.

All types are frozen dataclasses / enums — nothing in the pipeline mutates a
value in place; transforms return new objects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TranscriptSource(str, Enum):
    """How a transcript was obtained. No metadata-only path exists in v2 — a
    clip without a real transcript is never created (one of the old sins)."""

    MANUAL_CAPTIONS = "manual_captions"   # human-authored subtitles
    AUTO_CAPTIONS = "auto_captions"       # YouTube ASR


# Confidence weight per source — used downstream for ranking, never to fake a clip.
SOURCE_CONFIDENCE: dict[TranscriptSource, float] = {
    TranscriptSource.MANUAL_CAPTIONS: 0.95,
    TranscriptSource.AUTO_CAPTIONS: 0.85,
}


class Importance(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TranscriptStatus(str, Enum):
    """Lifecycle of a row in the pending_youtube_videos queue."""

    PENDING = "pending"           # discovered, awaiting a residential worker
    TRANSCRIBED = "transcribed"   # worker fetched transcript, awaiting extraction
    EXTRACTED = "extracted"       # clips extracted + stored
    NO_TRANSCRIPT = "no_transcript"  # no captions exist (terminal, not an error)
    FAILED = "failed"             # fetch/extract error (terminal until retried)


@dataclass(frozen=True)
class DiscoveredVideo:
    """A video found via RSS discovery — the unit written to the queue."""

    video_id: str
    title: str
    channel_id: str
    channel_name: str
    published_at: str  # ISO-8601 string from the Atom feed

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


@dataclass(frozen=True)
class TranscriptSegment:
    """One caption cue. ``start``/``duration`` are seconds (float)."""

    start: float
    duration: float
    text: str

    @property
    def end(self) -> float:
        return self.start + self.duration


@dataclass(frozen=True)
class Transcript:
    """A full fetched transcript. Always carries real timestamps."""

    video_id: str
    language: str          # BCP-47-ish code returned by YouTube (e.g. "te", "en")
    source: TranscriptSource
    segments: tuple[TranscriptSegment, ...]

    @property
    def is_auto(self) -> bool:
        return self.source is TranscriptSource.AUTO_CAPTIONS

    @property
    def duration_seconds(self) -> float:
        return self.segments[-1].end if self.segments else 0.0

    @property
    def char_count(self) -> int:
        return sum(len(s.text) for s in self.segments)


@dataclass(frozen=True)
class TranscriptFailure:
    """Typed failure — there are NO silent ``None`` returns in v2."""

    video_id: str
    reason: str   # machine key: "no_transcript" | "ip_blocked" | "unplayable" | "error"
    detail: str = ""


@dataclass(frozen=True)
class ExtractedClip:
    """A candidate clip from Groq, BEFORE quality gating / storage."""

    entity: str            # canonical entity name (validated downstream)
    start_seconds: int
    end_seconds: int
    summary: str           # English summary (validated downstream)
    importance: Importance


@dataclass(frozen=True)
class StoredClip:
    """A clip that passed every gate and is ready to insert."""

    video_id: str
    video_title: str
    channel_id: str
    channel_name: str
    video_published_at: str
    matched_entity: str
    clip_start_seconds: int
    clip_end_seconds: int
    summary: str
    transcript_segment: str
    transcript_language: str
    transcript_source: TranscriptSource
    confidence: float
    embedding: tuple[float, ...]
    importance: Importance

    @property
    def embed_url(self) -> str:
        """Deep-link that 'rolls the tape' at the mention. Real timestamp XOR
        full-video link is enforced by the storage gate before we get here."""
        return (
            f"https://www.youtube.com/watch?v={self.video_id}"
            f"&t={self.clip_start_seconds}s"
        )
