"""Quality harness: run the real extraction→gating→embedding path on a fetched
transcript and PRINT the resulting clips. Run inside rig-backend (Groq + LaBSE).

Does NOT write to the DB (persist=False) — it shows what would be stored so we
can eyeball quality.

Usage: python -m backend.collectors.youtube_v2._demo_extract /tmp/v6_transcript.json
"""
import asyncio
import json
import sys

from backend.collectors.youtube_v2.pipeline import (
    load_alias_block,
    load_entities,
    process_transcript,
    transcript_from_json,
)


async def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/v6_transcript.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    video_id = data["video_id"]
    transcript = transcript_from_json(video_id, data)
    print(
        f"Transcript: video={video_id} lang={transcript.language} "
        f"source={transcript.source.value} segments={len(transcript.segments)} "
        f"duration={transcript.duration_seconds:.0f}s\n"
    )

    from backend.database import get_db

    async with get_db() as db:
        entities = await load_entities(db)
        alias_block = await load_alias_block(db)
        print(f"Monitored entities: {len(entities)}\n")

        stored, metrics = await process_transcript(
            transcript,
            video_title="V6 News bulletin",
            channel_id="UCDCMjD1XIAsCZsYHNMGVcog",
            channel_name="V6 News Telugu",
            published_at="",
            entities=entities,
            alias_block=alias_block,
            db=db,
            persist=False,
        )

    print("=" * 70)
    print(f"CLIPS PRODUCED: {len(stored)}")
    print("=" * 70)
    for i, c in enumerate(stored, 1):
        print(f"\n[{i}] {c.matched_entity}  ({c.importance.value})  "
              f"{c.clip_start_seconds}-{c.clip_end_seconds}s")
        print(f"    summary: {c.summary}")
        print(f"    segment: {c.transcript_segment[:120]}")
        print(f"    embed:   {c.embed_url}")
        print(f"    lang={c.transcript_language} source={c.transcript_source.value} "
              f"conf={c.confidence} emb_dim={len(c.embedding)}")

    print("\n" + "=" * 70)
    print("METRICS:", json.dumps(metrics.summary(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
