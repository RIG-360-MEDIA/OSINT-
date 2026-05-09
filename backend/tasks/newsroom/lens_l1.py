"""
Lens L1 — YouTube auto-captions via yt-dlp.

Cheapest of the three lenses (free, no model, no LLM). Quality is
strong on English, decent on Hindi, weak on Telugu — which is why we
need L2 + L3 to triangulate.

Returns a list of segments with timestamps. If the video has no
auto-captions in the expected language, returns an empty list — the
reconcile step downgrades confidence accordingly but does not fail.
"""
from __future__ import annotations

import glob
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class L1Segment:
    start_sec: float
    end_sec: float
    text: str
    lang: str


def fetch_l1_segments(yt_video_id: str, language: str = "te") -> list[L1Segment]:
    """Pull auto-captions from YouTube for the given video.

    Args:
        yt_video_id: bare video id, e.g. "afX1BQu0DZ8"
        language:    BCP-47-ish ('te', 'hi', 'en'). Falls back to 'en'
                     if the requested language is missing.

    Returns:
        List of L1Segment, possibly empty.
    """
    url = f"https://www.youtube.com/watch?v={yt_video_id}"
    tmpdir = tempfile.mkdtemp(prefix=f"l1_{yt_video_id}_")
    try:
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--quiet",
            "--no-warnings",
            "--skip-download",
            "--write-auto-sub",
            "--sub-lang", f"{language},en",
            "--sub-format", "vtt",
            "-o", os.path.join(tmpdir, "%(id)s.%(ext)s"),
            url,
        ]
        proxy = os.getenv("YOUTUBE_PROXY_URL", "").strip()
        if proxy:
            cmd.extend(["--proxy", proxy])

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            logger.warning("L1 yt-dlp timed out for %s", yt_video_id)
            return []
        except subprocess.CalledProcessError as exc:
            logger.warning("L1 yt-dlp failed for %s: %s", yt_video_id, exc.stderr[:200])
            return []

        # Prefer the requested language, fall back to en
        for lang in (language, "en"):
            matches = glob.glob(os.path.join(tmpdir, f"*.{lang}.vtt"))
            if matches:
                segs = _parse_vtt(matches[0], lang)
                if segs:
                    return segs

        logger.info("L1 no captions for %s in %s/en", yt_video_id, language)
        return []
    finally:
        # Best-effort cleanup
        for f in glob.glob(os.path.join(tmpdir, "*")):
            try:
                os.remove(f)
            except OSError:
                pass
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass


def _parse_vtt(path: str, lang: str) -> list[L1Segment]:
    """Parse a WebVTT file into L1Segment list. Tolerant of YouTube's
    duplicate-line auto-caption format (each cue is repeated as it
    accumulates word-by-word — we keep only the final form per timestamp).
    """
    try:
        import webvtt  # noqa: F401  — already in backend/requirements.txt
        from webvtt import WebVTT
    except ImportError as exc:
        logger.error("webvtt-py not installed: %s", exc)
        return []

    out: list[L1Segment] = []
    seen_starts: set[float] = set()
    try:
        for caption in WebVTT().read(path):
            start = _vtt_to_sec(caption.start)
            end = _vtt_to_sec(caption.end)
            text = caption.text.strip()
            if not text:
                continue
            # Dedupe YouTube's word-by-word duplicates: keep last for each start
            if start in seen_starts:
                # replace the previous segment with the same start
                for i in range(len(out) - 1, -1, -1):
                    if out[i].start_sec == start:
                        out[i] = L1Segment(start_sec=start, end_sec=end, text=text, lang=lang)
                        break
            else:
                out.append(L1Segment(start_sec=start, end_sec=end, text=text, lang=lang))
                seen_starts.add(start)
    except Exception as exc:  # noqa: BLE001
        logger.warning("VTT parse failed for %s: %s", path, exc)
        return []

    return out


def _vtt_to_sec(t: str) -> float:
    """Parse "HH:MM:SS.mmm" or "MM:SS.mmm" → float seconds."""
    parts = t.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    if len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(t)


def join_l1_text(segs: Sequence[L1Segment]) -> str:
    """Concatenate L1 segment texts in order — useful for whole-VOD diff."""
    return " ".join(s.text for s in segs)
