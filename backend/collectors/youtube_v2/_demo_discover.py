"""List recent videos for channels (residential IP). Helps pick a politically
relevant video for the quality demo.

Usage: python -m backend.collectors.youtube_v2._demo_discover
"""
import asyncio

from backend.collectors.youtube_v2.discovery import discover_channel_videos

CHANNELS = {
    "V6 News": "UCDCMjD1XIAsCZsYHNMGVcog",
}


async def main() -> None:
    for name, cid in CHANNELS.items():
        try:
            vids = await discover_channel_videos(cid, max_results=15)
        except Exception as exc:  # noqa: BLE001
            print(f"{name}: ERROR {exc}")
            continue
        print(f"\n{name} ({len(vids)} videos):")
        for v in vids:
            print(f"  {v.video_id}  {v.title}")


if __name__ == "__main__":
    asyncio.run(main())
