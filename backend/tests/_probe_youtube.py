"""One-off probe: fetch V6 News videos, process the freshest, report why 0 clips.

Run inside the rig-backend container:
    docker exec rig-backend python -m backend.tests._probe_youtube
"""
import asyncio
import os

from sqlalchemy import text


async def main() -> None:
    from backend.collectors.youtube_collector import (
        _exhausted_api_keys,
        fetch_channel_videos,
        process_video,
    )
    from backend.database import get_db

    keys = [
        os.getenv(k)
        for k in (
            "YOUTUBE_API_KEY",
            "YOUTUBE_API_KEY_2",
            "YOUTUBE_API_KEY_3",
            "YOUTUBE_API_KEY_4",
            "YOUTUBE_API_KEY_5",
        )
    ]
    keys = [k for k in keys if k]
    print(f"available_keys={len(keys)}  exhausted_in_memory={len(_exhausted_api_keys)}")

    chan = "UCDCMjD1XIAsCZsYHNMGVcog"  # V6 News Telugu
    videos = await fetch_channel_videos(chan, keys, since_days=2, max_results=10)
    print(f"V6 News fetched: {len(videos)} videos")
    for v in videos[:5]:
        print(
            f"  vid={v.get('video_id')} pub={v.get('published_at')} "
            f"title={(v.get('title') or '')[:60]}"
        )
    if not videos:
        print("NO VIDEOS — that explains 0 clips")
        return

    async with get_db() as db:
        # entity_dictionary load (matches collector's normal path)
        ed_rows = (
            await db.execute(text("SELECT canonical_name FROM entity_dictionary"))
        ).fetchall()
        entity_dictionary = {r.canonical_name: True for r in ed_rows}
        print(f"entity_dictionary loaded: {len(entity_dictionary)} entries")

        ue_rows = (
            await db.execute(
                text("SELECT canonical_name FROM user_entities ORDER BY canonical_name")
            )
        ).fetchall()
        user_entities = [r.canonical_name for r in ue_rows]
        print(f"user_entities: {len(user_entities)}")

        # Find first video not yet in db
        target = None
        for v in videos:
            cnt = (
                await db.execute(
                    text("SELECT COUNT(*) c FROM youtube_clips WHERE video_id=:vid"),
                    {"vid": v["video_id"]},
                )
            ).fetchone().c
            print(f"  vid={v['video_id']}  existing_in_db={cnt}")
            if cnt == 0 and target is None:
                target = v

        if not target:
            print("ALL videos already in DB — every fresh video has at least one clip row")
            return

        print(
            f"PROCESSING {target['video_id']}  "
            f"title={(target.get('title') or '')[:60]}"
        )
        try:
            n = await process_video(target, chan, user_entities, entity_dictionary, db)
            await db.commit()
            print(f"process_video returned: {n} clips inserted")
        except Exception as exc:
            import traceback

            print(f"process_video EXCEPTION: {type(exc).__name__}: {exc}")
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
