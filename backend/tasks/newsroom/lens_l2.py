"""
Lens L2 — Groq Whisper API.

Groq exposes Whisper at audio.transcriptions; we use the same
GroqKeyManager from groq_client.py so quota / failover state is shared.

Model selection:
  - English-only:        whisper-large-v3-turbo (fastest, English-tuned)
  - Telugu / Hindi / mixed: whisper-large-v3 (multilingual)

Per Groq's audio API, the response includes word-level timestamps
when `timestamp_granularities=["segment"]` is requested. We parse
those into L2Segment list aligned with what L1/L3 produce.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.nlp.groq_client import groq_manager, GroqQuotaExhausted, GroqCallFailed

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class L2Segment:
    start_sec: float
    end_sec: float
    text: str
    lang: str
    avg_logprob: float | None = None


_MODEL_BY_LANG: dict[str, str] = {
    "en": "whisper-large-v3-turbo",
    "te": "whisper-large-v3",
    "hi": "whisper-large-v3",
}


async def fetch_l2_segments(audio_path: str, language: str = "te") -> list[L2Segment]:
    """Send audio to Groq Whisper, return L2 segments.

    Args:
        audio_path: local path to .m4a / .mp3 / .wav
        language:   ISO-639-1; routes to multilingual model for non-en.

    Returns:
        list of L2Segment. Empty list if Groq quota is exhausted (caller
        decides whether to surface that as a hard error or a degraded run).
    """
    model = _MODEL_BY_LANG.get(language, "whisper-large-v3")

    try:
        _idx, client = await groq_manager.get_key()
    except GroqQuotaExhausted:
        logger.warning("L2: Groq pool exhausted before transcription call")
        return []

    try:
        with open(audio_path, "rb") as fh:
            response = await client.audio.transcriptions.create(
                file=(audio_path, fh.read()),
                model=model,
                language=language if language in {"en", "te", "hi"} else None,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
                temperature=0.0,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("L2: Groq transcription failed: %s", exc)
        raise GroqCallFailed(f"L2 transcription error: {exc}") from exc

    segments_raw = getattr(response, "segments", None) or []
    out: list[L2Segment] = []
    for s in segments_raw:
        # Groq SDK returns dict-like objects; access via .get on a dict if needed
        if hasattr(s, "model_dump"):
            s = s.model_dump()
        elif not isinstance(s, dict):
            s = vars(s)
        text = (s.get("text") or "").strip()
        if not text:
            continue
        out.append(
            L2Segment(
                start_sec=float(s.get("start", 0.0)),
                end_sec=float(s.get("end", 0.0)),
                text=text,
                lang=language,
                avg_logprob=s.get("avg_logprob"),
            )
        )
    return out
