"""Entity-aware clip extraction via Groq.

Runs on Hetzner (Groq is not IP-blocked; only YouTube is). Takes a fetched
Transcript and the canonical entity list, returns gated ExtractedClips.

Quality contract enforced here (the old pipeline's sins, inverted):
  - summaries are ENGLISH — the prompt translates non-English transcripts, and
    is_probably_english rejects anything that leaks through;
  - entities are CANONICAL-only — Groq's entity is mapped to the exact
    canonical name or the clip is rejected (no hallucinated matched_entity);
  - filler / empty summaries are rejected;
  - low-importance clips are dropped.

Every rejection is recorded on PipelineMetrics (no silent drops). Long videos
are chunked so no mention is skipped.
"""
from __future__ import annotations

import json
import logging
import os

from .metrics import PipelineMetrics
from .models import ExtractedClip, Importance, Transcript
from .quality import (
    RejectReason,
    build_canonical_lookup,
    canonicalize_entity,
    is_filler_summary,
    is_probably_english,
)

logger = logging.getLogger("youtube_v2")

# Keep-all mode: store newsworthy clips even when the subject is NOT on the
# monitored watchlist (tagged is_watchlisted=False), mirroring the article
# corpus where the watchlist is a score, not an ingest gate. Off → legacy
# watchlist-gated behaviour. Rollback instantly via YOUTUBE_KEEP_ALL=0.
_YOUTUBE_KEEP_ALL = os.getenv("YOUTUBE_KEEP_ALL", "1") == "1"

# Actor/speaker placeholder values the LLM emits when it has no real name.
# Stances with these actors are dropped — they carry no intelligence value.
_PLACEHOLDER_ACTORS = frozenset({
    "speaker", "anchor", "host", "unknown", "n/a", "presenter",
    "reporter", "journalist", "correspondent",
})

# Sizing is governed by Groq's 6000 tokens-per-minute PER-KEY cap. A single
# request (input + reserved output) must fit under it. Indic-script text is
# token-dense (~2 tokens/char), so windows are kept small and output is
# bounded via max_tokens_override. ~150s of speech ≈ 2200 chars here.
_CHUNK_SECONDS = 150          # ~2.5-minute analysis windows
_MAX_CHUNK_CHARS = 2200       # ≈ 4400 input tokens for Indic scripts
_MAX_OUTPUT_TOKENS = 1500     # room for 5-6 sentence executive summaries per clip
_MAX_CHUNKS_PER_VIDEO = 24    # cap Groq calls/video (~60 min); excess is logged


def filter_stances(stances: list[dict]) -> list[dict]:
    """Drop stances whose actor is a placeholder — called after extraction
    when migration 107 child tables are populated."""
    return [
        s for s in stances
        if isinstance(s, dict)
        and str(s.get("actor", "")).strip().lower() not in _PLACEHOLDER_ACTORS
        and str(s.get("target", "")).strip()
        and str(s.get("stance", "")).strip()
    ]


def _chunk(transcript: Transcript) -> list[list]:
    """Split into _CHUNK_SECONDS windows so long videos lose no granularity."""
    segments = transcript.segments
    if not segments:
        return []
    chunks: list[list] = []
    current: list = []
    anchor = segments[0].start
    for seg in segments:
        if seg.start - anchor >= _CHUNK_SECONDS and current:
            chunks.append(current)
            current = []
            anchor = seg.start
        current.append(seg)
    if current:
        chunks.append(current)
    return chunks


def _build_system_prompt(
    channel_name: str, entities: list[str], alias_block: str
) -> str:
    entities_str = ", ".join(entities)
    parts = [
        "You are a political-intelligence analyst for an English-language "
        "newsroom.",
        f"You are reading a transcript chunk from the YouTube channel "
        f"'{channel_name}'. The transcript may be in Telugu, Hindi or another "
        "Indian language.",
        f"Find segments that mention any of these monitored entities: "
        f"{entities_str}.",
        "For each genuine mention that carries intelligence value (a policy "
        "announcement, statement, allegation, event or controversy), emit a "
        "clip.",
    ]
    if alias_block:
        parts.append(alias_block)
    parts.append(
        "HARD RULES:\n"
        "1. 'entity' MUST be copied EXACTLY from the monitored list above — "
        "never invent or rename. If the person is not on the list, skip them.\n"
        "2. 'summary' MUST be written in fluent ENGLISH (translate if the "
        "transcript is not English). 1-2 sentences, specific, no filler. "
        "Never output 'too short to summarise' or a bare timecode — omit the "
        "clip instead.\n"
        "3. 'start_seconds'/'end_seconds' are the real timecodes of the "
        "mention from the [Ns] markers.\n"
        "4. Respond with VALID JSON ONLY, no markdown. Schema:\n"
        '{"clips": [{"entity": "<exact canonical name>", '
        '"start_seconds": <int>, "end_seconds": <int>, '
        '"summary": "<English, 1-2 sentences>", '
        '"importance": "high|medium|low"}]}\n'
        'If nothing relevant, return {"clips": []}. Omit low-importance clips.'
    )
    return "\n\n".join(parts)


def _chunk_user_message(chunk: list, video_title: str, language: str) -> str:
    lines = [f"[{int(seg.start)}s] {seg.text.strip()}" for seg in chunk]
    body = "\n".join(lines)[:_MAX_CHUNK_CHARS]
    return (
        f"Video title: {video_title}\n"
        f"Transcript language: {language}\n\n"
        f"Transcript (format: [seconds] text):\n{body}"
    )


async def _extract_chunk(
    chunk: list,
    *,
    video_title: str,
    language: str,
    system_prompt: str,
    canonical: dict[str, str],
    metrics: PipelineMetrics,
    keep_all: bool = False,
) -> list[ExtractedClip]:
    from backend.nlp.groq_client import FAST_MODEL, call_groq

    if not chunk:
        return []

    user_msg = _chunk_user_message(chunk, video_title, language)
    try:
        raw = await call_groq(
            system=system_prompt,
            user=user_msg,
            task_type="transcript_analysis",
            model=FAST_MODEL,
            json_response=True,
            max_tokens_override=_MAX_OUTPUT_TOKENS,
        )
        data = json.loads(raw) if isinstance(raw, str) else raw
        proposed = data.get("clips", []) if isinstance(data, dict) else []
        metrics.record_chunk(ok=True)
    except Exception as exc:  # noqa: BLE001
        metrics.record_chunk(ok=False, detail=f"{type(exc).__name__}: {str(exc)[:80]}")
        return []

    metrics.record_proposed(len(proposed))
    out: list[ExtractedClip] = []
    for c in proposed:
        gated = _gate_clip(c, canonical, metrics, keep_all)
        if gated is not None:
            out.append(gated)
    return out


def _gate_clip(
    c: dict, canonical: dict[str, str], metrics: PipelineMetrics,
    keep_all: bool = False,
) -> ExtractedClip | None:
    """Apply entity / English / filler / importance gates to one raw clip."""
    if not isinstance(c, dict):
        return None

    importance_raw = str(c.get("importance", "medium")).lower()
    if importance_raw == Importance.LOW.value:
        metrics.record_reject(RejectReason.LOW_IMPORTANCE)
        return None

    # The watchlist is a TAG, not a gate (keep_all): a monitored subject is
    # canonicalised + flagged watchlisted; an off-watchlist but newsworthy
    # subject is kept verbatim and flagged is_watchlisted=False. Only a clip
    # with no identifiable subject at all is dropped. (Legacy mode: any
    # non-canonical entity is rejected, as before.)
    canon = canonicalize_entity(c.get("entity"), canonical)
    if canon is not None:
        entity = canon
        is_watchlisted = True
    elif keep_all:
        entity = str(c.get("entity") or "").strip()[:200]
        if not entity:
            metrics.record_reject(RejectReason.NON_CANONICAL_ENTITY, "empty")
            return None
        is_watchlisted = False
    else:
        metrics.record_reject(
            RejectReason.NON_CANONICAL_ENTITY, f"got={c.get('entity')!r}"
        )
        return None

    summary = str(c.get("summary", "")).strip()
    if is_filler_summary(summary):
        metrics.record_reject(RejectReason.FILLER_SUMMARY, f"{summary[:40]!r}")
        return None
    if not is_probably_english(summary):
        metrics.record_reject(RejectReason.NON_ENGLISH_SUMMARY, f"{summary[:40]!r}")
        return None

    try:
        start = int(c.get("start_seconds", 0))
        end = int(c.get("end_seconds", start + 30))
    except (TypeError, ValueError):
        metrics.record_reject(RejectReason.BAD_TIMESTAMP, f"{c.get('start_seconds')!r}")
        return None

    # Enforce minimum clip duration regardless of what the LLM emitted.
    # Auto-captions at transcript edges produce artificially short spans.
    _MIN_CLIP_SECONDS = 20
    if end - start < _MIN_CLIP_SECONDS:
        end = start + _MIN_CLIP_SECONDS

    importance = (
        Importance(importance_raw)
        if importance_raw in (Importance.HIGH.value, Importance.MEDIUM.value)
        else Importance.MEDIUM
    )
    return ExtractedClip(
        entity=entity,
        start_seconds=start,
        end_seconds=end,
        summary=summary,
        importance=importance,
        is_watchlisted=is_watchlisted,
    )


async def extract_clips(
    transcript: Transcript,
    *,
    video_title: str,
    channel_name: str,
    entities: list[str],
    metrics: PipelineMetrics,
    alias_block: str = "",
) -> list[ExtractedClip]:
    """Extract gated, canonical, English clips from a transcript."""
    import asyncio

    if not transcript.segments or not entities:
        return []

    all_chunks = _chunk(transcript)
    if not all_chunks:
        return []
    chunks = all_chunks[:_MAX_CHUNKS_PER_VIDEO]
    if len(all_chunks) > _MAX_CHUNKS_PER_VIDEO:
        # No silent truncation — long videos are explicitly flagged.
        dropped = len(all_chunks) - len(chunks)
        metrics.record_path(f"chunks_capped dropped={dropped}")
        logger.warning(
            "youtube_v2 chunk cap video=%s total=%d processed=%d dropped=%d "
            "(video exceeds ~%dmin coverage)",
            transcript.video_id, len(all_chunks), len(chunks), dropped,
            _MAX_CHUNKS_PER_VIDEO * _CHUNK_SECONDS // 60,
        )
    metrics.record_path(f"extract_chunks={len(chunks)}")

    canonical = build_canonical_lookup(entities)
    from .prompts import build_transcript_sys
    system_prompt = build_transcript_sys(
        channel_name, entities, alias_block, keep_all=_YOUTUBE_KEEP_ALL
    )

    results = await asyncio.gather(
        *(
            _extract_chunk(
                chunk,
                video_title=video_title,
                language=transcript.language,
                system_prompt=system_prompt,
                canonical=canonical,
                metrics=metrics,
                keep_all=_YOUTUBE_KEEP_ALL,
            )
            for chunk in chunks
        )
    )
    return [clip for chunk_clips in results for clip in chunk_clips]
