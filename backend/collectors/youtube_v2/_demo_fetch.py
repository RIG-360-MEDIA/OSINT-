"""Demo helper: fetch a transcript on the residential machine and dump it as
the worker's transcript_json. Run on the LAPTOP (residential IP).

Usage: python -m backend.collectors.youtube_v2._demo_fetch <video_id> <out.json>
"""
import json
import sys

from backend.collectors.youtube_v2.models import Transcript
from backend.collectors.youtube_v2.transcript import fetch_transcript


def main() -> None:
    video_id = sys.argv[1] if len(sys.argv) > 1 else "a7J4tyqD2cA"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "transcript.json"

    result = fetch_transcript(video_id)
    if not isinstance(result, Transcript):
        print(f"FAILURE: {result.reason} {result.detail}")
        sys.exit(1)

    payload = {
        "video_id": video_id,
        "language": result.language,
        "source": result.source.value,
        "segments": [
            {"start": s.start, "duration": s.duration, "text": s.text}
            for s in result.segments
        ],
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    print(
        f"OK video={video_id} lang={result.language} source={result.source.value} "
        f"segments={len(result.segments)} chars={result.char_count} -> {out_path}"
    )


if __name__ == "__main__":
    main()
