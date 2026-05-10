"""
Lens L3 — local CPU ASR via Faster-Whisper.

Free, fully offline, much slower than L2. Compensates for L2 outages
(rate-limit windows) and provides a third independent vote on each
segment so the reconcile step can detect lens-level errors.

Model size defaults to `medium` (~1.5GB on disk, ~3-4GB RAM at runtime,
fits the 4-core / 16GB Hetzner box with headroom). Tunable via env var
`NEWSROOM_L3_MODEL` (`small`, `medium`, `large-v3`). Upgrade to
`large-v3` requires ~10GB RAM — verify host headroom first.

Why not `small`: tested on Telugu fixture (afX1BQu0DZ8); produced
mangled output that pushed the reconcile LLM into hallucinated
entity matches downstream. `medium` is the smallest size that gives
acceptable Indic accuracy.

Singleton pattern: the model is loaded once per worker process and
reused for every call. Loading is heavy (~10s); reuse is essential.

NOTE: IndicConformer integration was scoped for this lens but skipped
in the v1 ship — Whisper's multilingual large-v3 handles Telugu and
Hindi acceptably and avoids the integration risk of plugging an
AI4Bharat HF model into pyctcdecode for tonight's verification.
This is documented as a known gap; tracked in
docs/newsroom/PROGRESS_NIGHT_OF_2026-05-09.md.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class L3Segment:
    start_sec: float
    end_sec: float
    text: str
    lang: str
    avg_logprob: float | None = None
    no_speech_prob: float | None = None


_MODEL_NAME = os.getenv("NEWSROOM_L3_MODEL", "medium")
_MODEL_LOCK = threading.Lock()
_MODEL = None  # populated on first call


def _get_model():
    """Lazy-load the Faster-Whisper model. Thread-safe; one model per
    process (Celery prefork puts each task in its own process anyway,
    so worst case is concurrency × model copies, but our whisper
    worker has concurrency=1)."""
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    with _MODEL_LOCK:
        if _MODEL is not None:
            return _MODEL
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper not installed. "
                "Add to backend/requirements.txt and rebuild rig-backend."
            ) from exc
        # int8 quantisation halves RAM with negligible quality loss
        # for small/medium; CPU-only execution is what we want here.
        logger.info("Loading Faster-Whisper model %s (CPU int8)", _MODEL_NAME)
        _MODEL = WhisperModel(_MODEL_NAME, device="cpu", compute_type="int8")
        logger.info("Faster-Whisper %s loaded", _MODEL_NAME)
        return _MODEL


def fetch_l3_segments(
    audio_path: str,
    language: str = "te",
    *,
    prompt_terms: str | None = None,
) -> list[L3Segment]:
    """Run Faster-Whisper on the audio, return per-segment text.

    Faster-Whisper auto-detects language if `language=None` is passed,
    but giving it the hint helps Telugu/Hindi where the detector can
    confuse for similar scripts. We pass the requested language as
    a hint; the model still self-corrects per chunk.

    `prompt_terms`: same idea as L2 — comma-separated proper-noun
    list passed as `initial_prompt`, biases the decoder toward
    correct spellings of regional politicians, places, parties.
    """
    model = _get_model()
    segments_iter, info = model.transcribe(
        audio_path,
        language=language if language in {"en", "te", "hi"} else None,
        beam_size=5,
        vad_filter=True,            # cuts long silences
        vad_parameters={"min_silence_duration_ms": 500},
        word_timestamps=False,
        initial_prompt=(prompt_terms[:200] if prompt_terms else None),
    )

    detected = info.language if info else language
    out: list[L3Segment] = []
    for seg in segments_iter:
        text = (seg.text or "").strip()
        if not text:
            continue
        out.append(
            L3Segment(
                start_sec=float(seg.start),
                end_sec=float(seg.end),
                text=text,
                lang=detected,
                avg_logprob=getattr(seg, "avg_logprob", None),
                no_speech_prob=getattr(seg, "no_speech_prob", None),
            )
        )
    return out
