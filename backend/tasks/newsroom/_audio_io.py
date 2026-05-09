"""
Audio I/O helpers for THE NEWSROOM 3-Lens pipeline.

Responsibilities:
  - Download a YouTube video's audio track to /tmp via yt-dlp
  - Probe duration with ffprobe
  - Clean up temp files

Output format is m4a (AAC) — small, widely supported by both Groq's
audio API and Faster-Whisper / pyannote.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AudioFile:
    path: str
    duration_sec: float | None
    yt_video_id: str
    yt_video_url: str


def download_youtube_audio(yt_video_id: str, *, max_duration_sec: int | None = None) -> AudioFile:
    """Download a YouTube video's audio track to /tmp.

    Raises subprocess.CalledProcessError if yt-dlp fails. Caller is
    responsible for cleanup() once done.

    `max_duration_sec` lets callers cap pulls (e.g. for live windows);
    None = full video.
    """
    url = f"https://www.youtube.com/watch?v={yt_video_id}"
    tmpdir = tempfile.mkdtemp(prefix=f"newsroom_{yt_video_id}_")
    out_template = os.path.join(tmpdir, "%(id)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--quiet",
        "--no-warnings",
        # bestaudio in m4a/aac when available, fall back to anything audio-only
        "-f", "bestaudio[ext=m4a]/bestaudio/best",
        "-x", "--audio-format", "m4a",
        "--no-progress",
        "-o", out_template,
        url,
    ]
    if max_duration_sec is not None:
        # yt-dlp supports --download-sections "*0-N" to grab a window
        cmd.extend(["--download-sections", f"*0-{max_duration_sec}"])

    proxy = os.getenv("YOUTUBE_PROXY_URL", "").strip()
    if proxy:
        cmd.extend(["--proxy", proxy])

    logger.info("yt-dlp downloading audio for %s", yt_video_id)
    subprocess.run(cmd, check=True, capture_output=True, text=True)

    # yt-dlp wrote one .m4a into tmpdir
    audio_path = None
    for fn in os.listdir(tmpdir):
        if fn.endswith(".m4a"):
            audio_path = os.path.join(tmpdir, fn)
            break
    if not audio_path:
        raise FileNotFoundError(
            f"yt-dlp completed but no .m4a found in {tmpdir} — "
            f"contents: {os.listdir(tmpdir)}"
        )

    duration = _probe_duration_sec(audio_path)
    return AudioFile(
        path=audio_path,
        duration_sec=duration,
        yt_video_id=yt_video_id,
        yt_video_url=url,
    )


def _probe_duration_sec(path: str) -> float | None:
    """Return audio duration in seconds, or None if ffprobe is unavailable / fails."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            check=True, capture_output=True, text=True,
        )
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as exc:
        logger.warning("ffprobe failed for %s: %s", path, exc)
        return None


def cleanup(audio: AudioFile) -> None:
    """Remove the tempdir holding the audio file. Always safe to call."""
    try:
        d = os.path.dirname(audio.path)
        if d and os.path.isdir(d) and d.startswith(tempfile.gettempdir()):
            shutil.rmtree(d, ignore_errors=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cleanup failed for %s: %s", audio.path, exc)
