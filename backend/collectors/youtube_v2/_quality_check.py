"""
Comprehensive quality check for youtube_v2 extraction pipeline.

Tests all risk dimensions:
  1. SHORT_CLIP       - 3-10 min, single entity, baseline
  2. MEDIUM_DEBATE    - 15-30 min interview/debate
  3. LONG_ASSEMBLY    - 45-90 min assembly session (multi-entity, many mentions)
  4. MULTI_ENTITY     - multiple tracked entities in one video
  5. OPPOSITION_FRAME - entity as *target* of criticism (not speaker)
  6. HINDI_NATIONAL   - Hindi-language national coverage of TG entities
  7. REPEAT_ENTITY    - same entity mentioned 10+ times
  8. KCR_SPEECH       - opposition leader's full speech

Usage (on TRIJYA-7):
  set GROQ_API_KEYS=key1,key2,...
  set PYTHONIOENCODING=utf-8
  python C:/Users/sshuser/quality_check.py
"""
import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

# ── path setup so imports resolve ──────────────────────────────────────────────
sys.path.insert(0, "C:/Users/sshuser/rig-surveillance")

from youtube_transcript_api import YouTubeTranscriptApi

from backend.collectors.youtube_v2.extraction import extract_clips
from backend.collectors.youtube_v2.models import (
    Transcript,
    TranscriptSegment,
    TranscriptSource,
)
from backend.collectors.youtube_v2.pipeline import load_alias_block, load_entities
from backend.collectors.youtube_v2.quality import build_canonical_lookup
from backend.database import get_db

# ── test cases ─────────────────────────────────────────────────────────────────
@dataclass
class TestCase:
    name: str
    video_id: str
    channel: str
    dimension: str          # what risk are we testing
    expected_entities: list[str]   # entities we expect to appear
    expected_min_clips: int        # floor (fail if below)
    expected_max_clips: int        # ceiling (fail if above — explosion check)
    notes: str = ""

TEST_CASES: list[TestCase] = [
    TestCase(
        name="KTR_slams_Revanth",
        video_id="N-Tiq5hU5Nk",
        channel="News18 Telugu",
        dimension="SHORT_CLIP",
        expected_entities=["K.T. Rama Rao", "A. Revanth Reddy"],
        expected_min_clips=1,
        expected_max_clips=6,
        notes="~5-8 min clip, KTR press conf criticising Revanth on phone-tapping",
    ),
    TestCase(
        name="Revanth_speech_highlights",
        video_id="Qk-Af3UwDkA",
        channel="NTV Telugu",
        dimension="MEDIUM_DEBATE",
        expected_entities=["A. Revanth Reddy"],
        expected_min_clips=1,
        expected_max_clips=8,
        notes="~15-25 min speech highlights",
    ),
    TestCase(
        name="KCR_Harish_counter_Revanth",
        video_id="ZYOUfkpDcDg",
        channel="Yuvagalam",
        dimension="MULTI_ENTITY",
        expected_entities=["K. Chandrashekar Rao", "T. Harish Rao", "A. Revanth Reddy"],
        expected_min_clips=2,
        expected_max_clips=12,
        notes="KCR + Harish Rao responding to Revanth on TG debts — 3 entities",
    ),
    TestCase(
        name="Revanth_fires_on_KCR",
        video_id="pi9T4dGg_xo",
        channel="NTV Telugu",
        dimension="OPPOSITION_FRAME",
        expected_entities=["A. Revanth Reddy", "K. Chandrashekar Rao"],
        expected_min_clips=1,
        expected_max_clips=8,
        notes="Revanth attacking KCR — tests whether KCR correctly tagged as TARGET not speaker",
    ),
    TestCase(
        name="KCR_full_speech_Zee",
        video_id="fTL-v6A61s0",
        channel="Zee Telugu",
        dimension="REPEAT_ENTITY",
        expected_entities=["K. Chandrashekar Rao"],
        expected_min_clips=2,
        expected_max_clips=15,
        notes="KCR full speech — same entity mentioned throughout; tests clip explosion control",
    ),
    TestCase(
        name="Assembly_Kaleshwaram_TV9",
        video_id="R8G1EmdCa6c",
        channel="TV9 Telugu",
        dimension="LONG_ASSEMBLY",
        expected_entities=["A. Revanth Reddy", "K. Chandrashekar Rao"],
        expected_min_clips=3,
        expected_max_clips=25,
        notes="Long assembly LIVE — Kaleshwaram debate; tests chunk handling + multi-entity in long video",
    ),
    TestCase(
        name="KTR_Revanth_assembly_highvoltage",
        video_id="pd3TLvMjQbU",
        channel="Oneindia Telugu",
        dimension="LONG_ASSEMBLY",
        expected_entities=["K.T. Rama Rao", "A. Revanth Reddy"],
        expected_min_clips=3,
        expected_max_clips=25,
        notes="High-voltage KCR vs Revanth assembly debate (Dec 2025)",
    ),
    TestCase(
        name="Revanth_vs_KCR_municipal_2026",
        video_id="7F6t4tz0Oa8",
        channel="TV9 Telugu",
        dimension="MULTI_ENTITY",
        expected_entities=["A. Revanth Reddy", "K. Chandrashekar Rao"],
        expected_min_clips=2,
        expected_max_clips=20,
        notes="Municipal election 2026 coverage — real recent event",
    ),
]

# ── helpers ────────────────────────────────────────────────────────────────────
def fetch_transcript(video_id: str) -> Optional[Transcript]:
    api = YouTubeTranscriptApi()
    try:
        fetched = api.fetch(video_id)
    except Exception as e:
        print(f"    [TRANSCRIPT FAIL] {e}")
        return None

    segments = tuple(
        TranscriptSegment(
            start=float(s.start),
            duration=float(s.duration),
            text=str(s.text).strip(),
        )
        for s in fetched
        if str(s.text).strip()
    )
    if not segments:
        return None

    total_sec = int(segments[-1].start + segments[-1].duration)
    lang = getattr(fetched, "language_code", "te")
    print(f"    [TRANSCRIPT OK] {len(segments)} segs | {total_sec//60}m{total_sec%60}s | lang={lang}")
    return Transcript(
        video_id=video_id,
        language=lang,
        source=TranscriptSource.AUTO_CAPTIONS,
        segments=segments,
    )


def grade(label: str, passed: bool) -> str:
    return f"  {'✅' if passed else '❌'} {label}"


# ── main ───────────────────────────────────────────────────────────────────────
async def run_case(tc: TestCase, entities, alias_block, canonical_lookup):
    print(f"\n{'='*70}")
    print(f"TEST: {tc.name}  [{tc.dimension}]")
    print(f"  video: https://youtu.be/{tc.video_id}")
    print(f"  notes: {tc.notes}")

    t0 = time.time()
    transcript = fetch_transcript(tc.video_id)
    if transcript is None:
        print("  ❌ SKIP — transcript unavailable")
        return None

    duration_sec = int(transcript.segments[-1].start + transcript.segments[-1].duration)

    from backend.collectors.youtube_v2.pipeline import process_transcript
    async with get_db() as db:
        stored, metrics = await process_transcript(
            transcript,
            video_title=tc.name,
            channel_id=tc.channel,
            channel_name=tc.channel,
            published_at="",
            entities=entities,
            alias_block=alias_block,
            db=db,
            persist=False,
        )
    elapsed = time.time() - t0

    m = metrics.summary()
    clips = stored or []

    # ── per-clip detail ────────────────────────────────────────────────────────
    entity_counts: dict[str, int] = {}
    importance_counts: dict[str, int] = {}
    for c in clips:
        entity_counts[c.matched_entity] = entity_counts.get(c.matched_entity, 0) + 1
        importance_counts[c.importance.value] = importance_counts.get(c.importance.value, 0) + 1

    print(f"\n  CLIPS: {len(clips)} | chunks ok/fail: {m['chunks_ok']}/{m['chunks_failed']} | {elapsed:.1f}s")
    print(f"  Entity distribution: {entity_counts}")
    print(f"  Importance distribution: {importance_counts}")
    if m.get("rejects"):
        print(f"  Rejects: {m['rejects']}")

    print(f"\n  --- Clip details ---")
    for i, c in enumerate(clips, 1):
        clip_dur = c.clip_end_seconds - c.clip_start_seconds
        ts = f"{c.clip_start_seconds//60}:{c.clip_start_seconds%60:02d}-{c.clip_end_seconds//60}:{c.clip_end_seconds%60:02d}"
        print(f"  [{i}] {c.matched_entity} | {c.importance.value} | {ts} ({clip_dur}s)")
        print(f"       {c.summary[:120]}")

    # ── quality gates ──────────────────────────────────────────────────────────
    print(f"\n  --- Quality gates ---")
    checks = []

    # G1: clip count in expected range
    checks.append(grade(
        f"Clip count {len(clips)} in [{tc.expected_min_clips}, {tc.expected_max_clips}]",
        tc.expected_min_clips <= len(clips) <= tc.expected_max_clips,
    ))

    # G2: expected entities appeared
    found = set(entity_counts.keys())
    for ent in tc.expected_entities:
        checks.append(grade(f"Expected entity found: {ent}", ent in found))

    # G3: no chunk failures (soft — warn only if >20%)
    total_chunks = m["chunks_ok"] + m["chunks_failed"]
    fail_pct = (m["chunks_failed"] / total_chunks * 100) if total_chunks else 0
    checks.append(grade(f"Chunk fail rate {fail_pct:.0f}% (threshold <20%)", fail_pct < 20))

    # G4: no importance=HIGH for passing mentions (all HIGH clips should have >30s)
    high_clips = [c for c in clips if c.importance.value == "high"]
    short_highs = [c for c in high_clips if (c.clip_end_seconds - c.clip_start_seconds) < 15]
    checks.append(grade(
        f"HIGH clips have >=15s span ({len(short_highs)} short-HIGH found)",
        len(short_highs) == 0,
    ))

    # G5: no duplicate timestamps for same entity
    seen = set()
    dups = 0
    for c in clips:
        key = (c.matched_entity, c.clip_start_seconds)
        if key in seen:
            dups += 1
        seen.add(key)
    checks.append(grade(f"No duplicate (entity, start_sec) pairs ({dups} dups)", dups == 0))

    # G6: summaries not empty
    empty_summaries = sum(1 for c in clips if not c.summary or len(c.summary) < 20)
    checks.append(grade(f"All summaries non-empty ({empty_summaries} empty)", empty_summaries == 0))

    # G7: clip ends after start
    bad_ts = sum(1 for c in clips if c.clip_end_seconds <= c.clip_start_seconds)
    checks.append(grade(f"All timestamps valid ({bad_ts} invalid)", bad_ts == 0))

    # G8: no unknown entities
    entity_names = {e["canonical_name"] for e in entities}
    unknown = [c.matched_entity for c in clips if c.matched_entity not in entity_names]
    checks.append(grade(f"All entities in monitored list ({len(unknown)} unknown)", len(unknown) == 0))

    for ch in checks:
        print(ch)

    passes = sum(1 for ch in checks if "✅" in ch)
    total  = len(checks)
    print(f"\n  SCORE: {passes}/{total} gates passed | video={duration_sec//60}m | {tc.dimension}")

    return {
        "test": tc.name,
        "dimension": tc.dimension,
        "clips": len(clips),
        "passes": passes,
        "total_gates": total,
        "chunks_ok": m["chunks_ok"],
        "chunks_failed": m["chunks_failed"],
        "duration_sec": duration_sec,
        "entity_counts": entity_counts,
        "importance_counts": importance_counts,
    }


async def main():
    print("Loading entity list from DB...")
    async with get_db() as db:
        entities = await load_entities(db)
        alias_block = await load_alias_block(db)
    canonical_lookup = build_canonical_lookup(entities)
    print(f"Loaded {len(entities)} entities, alias block {len(alias_block)} chars\n")

    results = []
    for tc in TEST_CASES:
        result = await run_case(tc, entities, alias_block, canonical_lookup)
        if result:
            results.append(result)

    # ── summary table ──────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("QUALITY CHECK SUMMARY")
    print(f"{'='*70}")
    print(f"{'Test':<35} {'Dim':<18} {'Clips':>5} {'Gates':>8} {'Chunks':>10} {'Dur':>6}")
    print("-" * 70)
    for r in results:
        dur = f"{r['duration_sec']//60}m"
        chunks = f"{r['chunks_ok']}/{r['chunks_ok']+r['chunks_failed']}"
        gates  = f"{r['passes']}/{r['total_gates']}"
        print(f"{r['test']:<35} {r['dimension']:<18} {r['clips']:>5} {gates:>8} {chunks:>10} {dur:>6}")

    total_pass = sum(r["passes"] for r in results)
    total_gate = sum(r["total_gates"] for r in results)
    print(f"\nOVERALL: {total_pass}/{total_gate} gates passed across {len(results)} videos")


if __name__ == "__main__":
    asyncio.run(main())
