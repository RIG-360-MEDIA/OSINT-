"""Live path harness (Hetzner side): take a captured audio clip → Groq Whisper
→ extraction → clips. Proves the live audio path end to end.

Usage: python -m backend.collectors.youtube_v2._demo_live_extract /tmp/hi_live.mp3 <label>
"""
import asyncio
import os
import sys

import httpx

from backend.collectors.youtube_v2.models import (
    Transcript,
    TranscriptSegment,
    TranscriptSource,
)
from backend.collectors.youtube_v2.pipeline import (
    load_alias_block,
    load_entities,
    process_transcript,
)


def whisper_transcribe(path: str) -> tuple[str, list]:
    """Groq whisper-large-v3 → (language, segments[{start,end,text}])."""
    keys = [k.strip() for k in os.getenv("GROQ_API_KEYS", "").split(",") if k.strip()]
    last = ""
    for key in keys[:6]:
        with open(path, "rb") as fh:
            files = {"file": ("audio.mp3", fh, "audio/mpeg")}
            data = {"model": "whisper-large-v3", "response_format": "verbose_json",
                    "temperature": "0"}
            r = httpx.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                files=files, data=data,
                headers={"Authorization": f"Bearer {key}"}, timeout=120,
            )
        if r.status_code == 200:
            j = r.json()
            return j.get("language", "auto"), j.get("segments", [])
        last = f"HTTP {r.status_code} {r.text[:120]}"
    raise RuntimeError(f"all keys failed: {last}")


async def main() -> None:
    path = sys.argv[1]
    label = sys.argv[2] if len(sys.argv) > 2 else "LIVE"

    language, segs = whisper_transcribe(path)
    tsegs = tuple(
        TranscriptSegment(
            start=float(s.get("start", 0)),
            duration=float(s.get("end", 0)) - float(s.get("start", 0)),
            text=str(s.get("text", "")).strip(),
        )
        for s in segs if s.get("text")
    )
    print(f"Whisper: lang={language} segments={len(tsegs)} "
          f"chars={sum(len(s.text) for s in tsegs)}")
    if tsegs:
        print(f"  raw sample: {tsegs[0].text[:90]!r}")

    transcript = Transcript(
        video_id=label, language=language,
        source=TranscriptSource.AUTO_CAPTIONS, segments=tsegs,
    )

    from backend.database import get_db
    async with get_db() as db:
        entities = await load_entities(db)
        alias = await load_alias_block(db)
        stored, metrics = await process_transcript(
            transcript, video_title=f"LIVE {label}", channel_id="live",
            channel_name="LIVE", published_at="", entities=entities,
            alias_block=alias, db=db, persist=False,
        )

    print("=" * 64)
    print(f"LIVE CLIPS ({label}): {len(stored)}")
    print("=" * 64)
    for i, c in enumerate(stored, 1):
        print(f"\n[{i}] {c.matched_entity} ({c.importance.value}) {c.clip_start_seconds}-{c.clip_end_seconds}s")
        print(f"    summary: {c.summary}")
    print("\nMETRICS:", metrics.summary())


if __name__ == "__main__":
    asyncio.run(main())
