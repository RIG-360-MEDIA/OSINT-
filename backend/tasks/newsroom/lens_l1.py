"""
Lens L1 — YouTube auto-captions via youtube_transcript_api.

Mirrors the production pattern in backend.collectors.youtube_collector
.fetch_transcript() — the instance API of `youtube_transcript_api`
(class.fetch(video_id, languages=[...])) with cookies + proxy passthrough,
which bypasses many of the data-center bot challenges that hit yt-dlp.

Quality is strong on English, decent on Hindi, weak on Telugu — which
is why we need L2 + L3 to triangulate. Returns an empty list on
RequestBlocked / NoTranscriptFound — the reconcile step downgrades
confidence accordingly but does not fail.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

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
        language:    BCP-47-ish ('te', 'hi', 'en'). Falls back to others
                     if the requested language is missing.

    Returns:
        List of L1Segment, possibly empty.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        logger.error("youtube_transcript_api not installed: %s", exc)
        return []

    cookies = os.getenv("YOUTUBE_COOKIES_PATH", "").strip()
    proxy = os.getenv("YOUTUBE_PROXY_URL", "").strip()

    api_kwargs: dict = {}
    if cookies and os.path.exists(cookies):
        api_kwargs["cookies"] = cookies
    if proxy:
        try:
            from youtube_transcript_api.proxies import GenericProxyConfig
            api_kwargs["proxy_config"] = GenericProxyConfig(
                http_url=proxy, https_url=proxy,
            )
        except ImportError:
            pass

    try:
        api = YouTubeTranscriptApi(**api_kwargs)
    except TypeError:
        # Older library versions don't accept kwargs
        api = YouTubeTranscriptApi()

    # Try the requested language first, then sensible fallbacks
    candidates = [language] + [l for l in ("en", "te", "hi", "kn", "ta") if l != language]

    for lang in candidates:
        try:
            data = api.fetch(yt_video_id, languages=[lang])
        except Exception as exc:
            cls = exc.__class__.__name__
            if cls in {"RequestBlocked", "IpBlocked", "RequestBlockedByYouTube"}:
                logger.warning(
                    "L1: IP-blocked fetching %s (%s); giving up on this video",
                    yt_video_id, lang,
                )
                return []
            # NoTranscriptFound / TranscriptsDisabled / VideoUnplayable etc.
            continue

        out: list[L1Segment] = []
        prev_end = 0.0
        for item in data:
            text = (getattr(item, "text", "") or "").strip()
            if not text:
                continue
            start = float(getattr(item, "start", 0.0) or 0.0)
            duration = float(getattr(item, "duration", 0.0) or 0.0)
            end = start + duration
            # Some YouTube auto-caption streams produce overlapping
            # cues; clip end to ≥ start so reconcile-overlap math is sane.
            if end < start:
                end = start
            out.append(L1Segment(start_sec=start, end_sec=end, text=text, lang=lang))
            prev_end = end
        return out

    logger.info("L1 no captions for %s in any of %s", yt_video_id, candidates)
    return []
