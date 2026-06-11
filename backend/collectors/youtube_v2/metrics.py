"""Observability — no silent fallbacks.

Every drop, fallback and path choice increments a counter and (for drops) logs
a WARNING with the reason. This directly answers the old sin where the Whisper
fallback was dead for 1445 clips and nobody knew because failures logged at
DEBUG.

``PipelineMetrics`` is mutated in place deliberately — it is a local
accumulator, not domain data — but it is only ever touched through its own
record_* methods, which keeps the mutation contained and observable.
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

from .quality import RejectReason

logger = logging.getLogger("youtube_v2")


@dataclass
class PipelineMetrics:
    """Per-run counters. One instance per video (or per batch)."""

    video_id: str
    clips_proposed: int = 0
    clips_stored: int = 0
    chunks_ok: int = 0
    chunks_failed: int = 0
    rejects: Counter = field(default_factory=Counter)
    path_used: Counter = field(default_factory=Counter)

    def record_chunk(self, *, ok: bool, detail: str = "") -> None:
        """Record whether a Groq chunk call succeeded. A failed chunk is a
        coverage hole — never invisible (the old Whisper-dead-for-1445-clips sin)."""
        if ok:
            self.chunks_ok += 1
        else:
            self.chunks_failed += 1
            logger.warning(
                "youtube_v2 chunk_failed video=%s %s", self.video_id, detail
            )

    def record_path(self, path: str) -> None:
        """Record which transcript/extraction path was taken (captions vs auto,
        chunk count, etc.). Always visible — never a silent choice."""
        self.path_used[path] += 1
        logger.info("youtube_v2 path video=%s path=%s", self.video_id, path)

    def record_proposed(self, n: int) -> None:
        self.clips_proposed += n

    def record_reject(self, reason: RejectReason, detail: str = "") -> None:
        """Record + WARN on every dropped clip. The audit's invisible failures
        become visible here."""
        self.rejects[reason.value] += 1
        logger.warning(
            "youtube_v2 reject video=%s reason=%s %s",
            self.video_id, reason.value, detail,
        )

    def record_stored(self, n: int = 1) -> None:
        self.clips_stored += n

    def summary(self) -> dict[str, object]:
        return {
            "video_id": self.video_id,
            "chunks_ok": self.chunks_ok,
            "chunks_failed": self.chunks_failed,
            "proposed": self.clips_proposed,
            "stored": self.clips_stored,
            "rejected": sum(self.rejects.values()),
            "rejects": dict(self.rejects),
            "paths": dict(self.path_used),
        }

    def log_summary(self) -> None:
        logger.info("youtube_v2 summary %s", self.summary())
