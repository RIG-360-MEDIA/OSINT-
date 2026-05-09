"""
Audio I/O helpers for THE NEWSROOM 3-Lens pipeline.

Uses yt_dlp's Python API (not subprocess) to match the production
pattern in backend.collectors.youtube_collector — same cookies +
proxy passthrough, same format selector, same anti-bot handling.

Output format is m4a (AAC) — small, widely supported by both Groq's
audio API and Faster-Whisper / pyannote.
"""
from __future__ import annotations

import asyncio
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


def _cookies_path() -> str | None:
    """Return YOUTUBE_COOKIES_PATH if set and the file exists, else None."""
    p = os.getenv("YOUTUBE_COOKIES_PATH", "").strip()
    if p and os.path.exists(p):
        return p
    return None


def _proxy_url() -> str | None:
    p = os.getenv("YOUTUBE_PROXY_URL", "").strip()
    return p or None


async def download_youtube_audio(
    yt_video_id: str,
    *,
    max_duration_sec: int | None = None,
) -> AudioFile:
    """Download a YouTube video's audio track to /tmp.

    Uses the yt_dlp Python API (matches backend.collectors.youtube_collector
    pattern) with cookies + proxy. Caller is responsible for cleanup().
    """
    import yt_dlp                                  # imported lazily

    url = f"https://www.youtube.com/watch?v={yt_video_id}"
    tmpdir = tempfile.mkdtemp(prefix=f"newsroom_{yt_video_id}_")
    audio_path = os.path.join(tmpdir, f"{yt_video_id}.m4a")

    # Format selector: prefer m4a, fall through to any audio-only stream,
    # last fallback is any stream that contains audio (production-tested
    # selector from youtube_collector.py L946).
    ydl_opts: dict = {
        "format":      "bestaudio[ext=m4a]/bestaudio/best[acodec!=none]/best",
        "outtmpl":     audio_path,
        "quiet":       True,
        "no_warnings": True,
    }
    if max_duration_sec is not None:
        ydl_opts["match_filter"] = yt_dlp.utils.match_filter_func(
            f"duration <= {max_duration_sec}"
        )
    cp = _cookies_path()
    if cp:
        ydl_opts["cookiefile"] = cp
    pu = _proxy_url()
    if pu:
        ydl_opts["proxy"] = pu

    logger.info("yt-dlp downloading audio for %s", yt_video_id)
    try:
        def _do_download() -> None:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        await asyncio.to_thread(_do_download)
    except Exception as exc:
        # Surface a clean error so process_broadcast can log it once
        # without a 50-line yt-dlp traceback.
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise RuntimeError(
            f"yt-dlp audio download failed for {yt_video_id}: {exc}"
        ) from exc

    if not os.path.exists(audio_path):
        # Fall back to scanning the dir — yt-dlp may have written under
        # a different extension if `bestaudio[ext=m4a]` didn't match.
        candidates = [f for f in os.listdir(tmpdir) if not f.endswith(".part")]
        if candidates:
            audio_path = os.path.join(tmpdir, candidates[0])
        else:
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise FileNotFoundError(
                f"yt-dlp produced no audio file for {yt_video_id} in {tmpdir}"
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
