"""
Speaker diarisation — pyannote.audio when HF_TOKEN is configured,
otherwise a single-speaker stub.

The full implementation uses pyannote/speaker-diarization-3.1, which is
a gated HuggingFace model — accessing it requires accepting the
license on huggingface.co and configuring HF_TOKEN in .env.prod.

Until that's done, every segment is labelled SPEAKER_01 and downstream
phonetic_snap still works (it matches the *content* of the segment, not
the speaker_label, so DOSSIER's "speakers we follow" view will simply
look thin until real diarisation is enabled).

Returns a list of (start_sec, end_sec, speaker_label) turns; segments
are intersected with these turns by timestamp overlap in process_broadcast.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpeakerTurn:
    start_sec: float
    end_sec: float
    speaker_label: str


def diarise(audio_path: str, total_duration_sec: float | None = None) -> list[SpeakerTurn]:
    """Return a list of speaker turns covering the audio.

    Falls back to a single SPEAKER_01 turn covering [0, total_duration]
    when HF_TOKEN is not configured.
    """
    hf_token = os.getenv("HF_TOKEN", "").strip()
    if not hf_token:
        return _single_speaker_stub(total_duration_sec)

    try:
        from pyannote.audio import Pipeline
    except ImportError:
        logger.warning("pyannote.audio not installed — falling back to single-speaker stub")
        return _single_speaker_stub(total_duration_sec)

    try:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("pyannote model load failed: %s — falling back to stub", exc)
        return _single_speaker_stub(total_duration_sec)

    diarisation = pipeline(audio_path)
    out: list[SpeakerTurn] = []
    for turn, _, label in diarisation.itertracks(yield_label=True):
        out.append(
            SpeakerTurn(
                start_sec=float(turn.start),
                end_sec=float(turn.end),
                speaker_label=str(label),
            )
        )
    return out


def _single_speaker_stub(total_duration_sec: float | None) -> list[SpeakerTurn]:
    duration = total_duration_sec if total_duration_sec is not None else 1e9
    return [SpeakerTurn(start_sec=0.0, end_sec=duration, speaker_label="SPEAKER_01")]


def speaker_for_time(turns: list[SpeakerTurn], midpoint_sec: float) -> str:
    """Return the speaker label whose turn contains midpoint_sec.

    Used by process_broadcast to assign a speaker to each transcript
    segment. If no turn contains the timestamp, returns the closest
    one's label.
    """
    if not turns:
        return "SPEAKER_01"
    for t in turns:
        if t.start_sec <= midpoint_sec <= t.end_sec:
            return t.speaker_label
    # Fall through — pick nearest
    closest = min(
        turns,
        key=lambda t: min(abs(t.start_sec - midpoint_sec), abs(t.end_sec - midpoint_sec)),
    )
    return closest.speaker_label
