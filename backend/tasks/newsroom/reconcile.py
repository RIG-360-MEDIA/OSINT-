"""
3-Lens Consensus reconciliation.

Inputs: per-segment text from L1 (yt-dlp captions), L2 (Groq Whisper),
L3 (Faster-Whisper local).

Strategy: L2 is the timeline source-of-truth (Groq Whisper produces
clean sentence-level segmentation with reliable timestamps). For each
L2 segment, we pull the time-overlapping text from L1 and L3, and ask
Groq (with automatic Cerebras failover from groq_client.py) to merge
them into one canonical sentence with a confidence rating.

Reconciled in batches of 8 segments per LLM call to keep token usage
sane on Cerebras' 1M-tokens/day quota — one VOD of ~30 minutes
typically reconciles in 25–40 calls and ~30 K tokens.

Output: list of ReconciledSegment with canonical text in source
language, English translation, confidence, and the original 3 lens
texts retained verbatim for audit.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from backend.nlp.groq_client import call_groq, GroqCallFailed, GroqQuotaExhausted
from backend.tasks.newsroom.lens_l1 import L1Segment
from backend.tasks.newsroom.lens_l2 import L2Segment
from backend.tasks.newsroom.lens_l3 import L3Segment

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconciledSegment:
    start_sec: float
    end_sec: float
    text_native: str
    text_en: str | None
    confidence: float       # 0.0 – 1.0
    l1_text: str | None
    l2_text: str
    l3_text: str | None
    lang: str


_BATCH_SIZE = 8
_RECONCILE_SYSTEM = (
    "You are a transcription reconciliation engine. You receive 3 candidate "
    "transcripts of the same audio chunk produced by 3 different ASR systems. "
    "Output the most likely canonical version, preserving proper-noun spelling "
    "(political names, places, parties — KCR, Revanth Reddy, BJP, Hyderabad, etc.). "
    "Mark low-confidence words by enclosing them in ~~tildes~~. "
    "Also produce a clean English translation. "
    "Output STRICT JSON only — no prose, no markdown."
)


def reconcile_segments(
    l1_segs: list[L1Segment],
    l2_segs: list[L2Segment],
    l3_segs: list[L3Segment],
    *,
    language: str = "te",
) -> list[ReconciledSegment]:
    """Synchronous wrapper used by the Celery orchestrator. Drives
    the async LLM calls under the hood."""
    import asyncio
    return asyncio.run(_reconcile_async(l1_segs, l2_segs, l3_segs, language=language))


async def _reconcile_async(
    l1_segs: list[L1Segment],
    l2_segs: list[L2Segment],
    l3_segs: list[L3Segment],
    *,
    language: str,
) -> list[ReconciledSegment]:
    if not l2_segs:
        # L2 timeline is missing. Fall back to L3 timeline.
        if not l3_segs:
            logger.warning("reconcile: both L2 and L3 empty; nothing to reconcile")
            return []
        l2_proxy = [
            L2Segment(start_sec=s.start_sec, end_sec=s.end_sec, text=s.text, lang=s.lang)
            for s in l3_segs
        ]
        l2_segs = l2_proxy

    # Pre-compute L1 / L3 lookups by overlap to L2.
    overlaps_l1 = [_best_overlap_text(seg, l1_segs) for seg in l2_segs]
    overlaps_l3 = [_best_overlap_text(seg, l3_segs) for seg in l3_segs]
    # L3 might have different segmentation; align by L2 timestamps:
    overlaps_l3 = [_best_overlap_text(seg, l3_segs) for seg in l2_segs]

    out: list[ReconciledSegment] = []
    for batch_start in range(0, len(l2_segs), _BATCH_SIZE):
        batch_l2 = l2_segs[batch_start:batch_start + _BATCH_SIZE]
        batch_l1 = overlaps_l1[batch_start:batch_start + _BATCH_SIZE]
        batch_l3 = overlaps_l3[batch_start:batch_start + _BATCH_SIZE]

        try:
            merged = await _reconcile_batch(batch_l2, batch_l1, batch_l3, language=language)
        except (GroqQuotaExhausted, GroqCallFailed) as exc:
            logger.warning(
                "reconcile: LLM call failed (%s) — degrading to L2-only canonical for this batch",
                exc,
            )
            merged = [
                {"text_native": l2.text, "text_en": None, "confidence": 0.55}
                for l2 in batch_l2
            ]

        for l2, l1, l3, m in zip(batch_l2, batch_l1, batch_l3, merged):
            out.append(
                ReconciledSegment(
                    start_sec=l2.start_sec,
                    end_sec=l2.end_sec,
                    text_native=m.get("text_native") or l2.text,
                    text_en=m.get("text_en"),
                    confidence=float(m.get("confidence", 0.6)),
                    l1_text=l1,
                    l2_text=l2.text,
                    l3_text=l3,
                    lang=language,
                )
            )

    return out


def _best_overlap_text(target, candidates) -> str | None:
    """Return the text of the candidate segment with the largest time
    overlap to `target`. None if zero overlap."""
    if not candidates:
        return None
    best = None
    best_overlap = 0.0
    for c in candidates:
        overlap = max(
            0.0,
            min(target.end_sec, c.end_sec) - max(target.start_sec, c.start_sec),
        )
        if overlap > best_overlap:
            best_overlap = overlap
            best = c
    return best.text if best else None


async def _reconcile_batch(
    l2_batch,
    l1_batch,
    l3_batch,
    *,
    language: str,
) -> list[dict]:
    """Send one batch of segments to Groq/Cerebras for reconciliation."""
    items = []
    for i, (l2, l1, l3) in enumerate(zip(l2_batch, l1_batch, l3_batch)):
        items.append({
            "i": i,
            "l1": l1 or "",
            "l2": l2.text,
            "l3": l3 or "",
        })

    user_prompt = (
        f"Source language: {language}.\n"
        f"For each item, output one entry in `merged` keyed by the same i.\n"
        "Each entry: {\"text_native\": str, \"text_en\": str, \"confidence\": float (0..1)}.\n"
        "If the lenses agree closely, confidence should be high (0.85+). "
        "If they diverge, confidence drops (0.4–0.6) and you should pick the "
        "most plausible reading.\n"
        f"Items:\n{json.dumps(items, ensure_ascii=False)}\n"
        "Respond with: {\"merged\": {\"0\": {...}, \"1\": {...}, ...}}"
    )

    raw = await call_groq(
        system=_RECONCILE_SYSTEM,
        user=user_prompt,
        task_type="brief_generation",   # gets the 4000-token cap
        json_response=True,
    )

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("reconcile: LLM returned non-JSON (%s); using L2 verbatim", exc)
        return [{"text_native": l2.text, "text_en": None, "confidence": 0.55} for l2 in l2_batch]

    merged = parsed.get("merged", {}) if isinstance(parsed, dict) else {}
    out: list[dict] = []
    for i in range(len(l2_batch)):
        entry = merged.get(str(i)) or merged.get(i) or {}
        if not isinstance(entry, dict):
            entry = {}
        out.append(entry)
    return out
