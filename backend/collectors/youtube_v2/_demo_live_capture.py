"""Capture N seconds of a LIVE stream's audio (runs on TRIJYA-7, residential IP).

Pulls the live audio URL via yt-dlp, records the live edge with ffmpeg into a
small mono 16 kHz mp3 — Whisper-friendly and tiny to ship.

Usage: python _demo_live_capture.py <video_id> <out.mp3> [seconds]
"""
import os
import subprocess
import sys

import imageio_ffmpeg
import yt_dlp


def main() -> None:
    vid = sys.argv[1]
    out = sys.argv[2]
    dur = int(sys.argv[3]) if len(sys.argv) > 3 else 60
    url = f"https://www.youtube.com/watch?v={vid}"

    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "format": "bestaudio/best"}) as ydl:
        info = ydl.extract_info(url, download=False)
    audio_url = info.get("url")
    is_live = info.get("is_live")
    title = (info.get("title") or "")[:60]
    if not audio_url:
        print(f"FAIL no audio url; is_live={is_live}")
        sys.exit(1)

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ff, "-y", "-i", audio_url, "-t", str(dur),
           "-vn", "-ar", "16000", "-ac", "1", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    size = os.path.getsize(out) if os.path.exists(out) else 0
    print(f"is_live={is_live} title={title!r} rc={r.returncode} bytes={size}")
    if r.returncode != 0 or size == 0:
        print(r.stderr[-600:])
        sys.exit(1)
    print(f"OK captured {dur}s -> {out}")


if __name__ == "__main__":
    main()
