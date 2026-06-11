"""Transcript fetch via youtube-transcript-api.

RUNS ON A RESIDENTIAL WORKER OR BEHIND A PROXY. YouTube hard-blocks datacenter
IPs (Hetzner, Cloudflare) from the timed-text endpoint. Route around this via:
  - WEBSHARE_USER + WEBSHARE_PASS  → Webshare rotating proxy (free or paid)
  - YT_PROXY                       → any generic HTTP proxy URL

If neither is set, falls back to direct (works from residential IPs only).

Returns a Transcript on success or a typed TranscriptFailure on any miss — no
silent None. Distinguishes "no captions exist" (terminal, not an error) from
"IP blocked" (retryable elsewhere) so the queue can route correctly.

Targets youtube-transcript-api ≥ 1.2 (instance API: ``api.list`` /
``api.fetch`` returning objects with ``.language_code`` / ``.is_generated``).
"""
from __future__ import annotations

import itertools
import logging
import os

from .models import (
    Transcript,
    TranscriptFailure,
    TranscriptSegment,
    TranscriptSource,
)

logger = logging.getLogger("youtube_v2")

# Round-robin cursor over the YT_RELAY_URL pool (one entry per distinct-IP relay).
_relay_rr = itertools.count()


def _make_api():
    from youtube_transcript_api import YouTubeTranscriptApi

    webshare_user = os.getenv("WEBSHARE_USER", "").strip()
    webshare_pass = os.getenv("WEBSHARE_PASS", "").strip()
    yt_proxy      = os.getenv("YT_PROXY", "").strip()

    if webshare_user and webshare_pass:
        from youtube_transcript_api.proxies import WebshareProxyConfig
        logger.debug("youtube_v2 transcript using Webshare proxy")
        return YouTubeTranscriptApi(
            proxy_config=WebshareProxyConfig(
                proxy_username=webshare_user,
                proxy_password=webshare_pass,
            )
        )
    if yt_proxy:
        from youtube_transcript_api.proxies import GenericProxyConfig
        logger.debug("youtube_v2 transcript using generic proxy %s", yt_proxy[:30])
        return YouTubeTranscriptApi(
            proxy_config=GenericProxyConfig(http_url=yt_proxy, https_url=yt_proxy)
        )
    return YouTubeTranscriptApi()

# Preferred caption languages, in order. We accept the source language even if
# non-English — extraction translates to English downstream. English captions
# are simply preferred when present.
_PREFERRED_LANGS = ("en", "en-US", "en-GB", "te", "hi", "kn", "ta", "ur")

_BLOCK_MARKERS = ("Blocked", "IpBlocked", "RequestBlocked", "TooManyRequests")
_NO_TRANSCRIPT_MARKERS = ("NoTranscriptFound", "TranscriptsDisabled")
_UNPLAYABLE_MARKERS = ("VideoUnplayable", "VideoUnavailable")


def _fetch_via_relay(video_id: str, relay_url: str) -> Transcript | TranscriptFailure:
    """Call the transcript relay service instead of hitting YouTube directly.

    The relay runs on a residential machine and handles all rate limiting,
    retries, and circuit breaking. Set YT_RELAY_URL to its base URL.
    """
    import requests as _req  # noqa: PLC0415

    url = f"{relay_url.rstrip('/')}/fetch/{video_id}"
    try:
        r    = _req.get(url, timeout=120)
        data = r.json()
    except Exception as exc:
        logger.warning("youtube_v2 relay video=%s error=%s", video_id, exc)
        return TranscriptFailure(video_id, "error", f"relay_unreachable: {exc}")

    if not data.get("ok"):
        reason = (data.get("reason") or "unknown").lower()
        if "circuit_open" in reason:
            retry = data.get("retry_after", 0)
            logger.warning("youtube_v2 relay video=%s circuit_open retry_after=%ds", video_id, retry)
            return TranscriptFailure(video_id, "ip_blocked", f"relay circuit open ({retry}s)")
        if any(m in reason for m in ("no_transcript", "empty_transcript", "notranscriptfound", "transcriptsdisabled")):
            return TranscriptFailure(video_id, "no_transcript", reason)
        if any(m in reason for m in ("videounplayable", "videounavailable")):
            return TranscriptFailure(video_id, "unplayable", reason)
        return TranscriptFailure(video_id, "ip_blocked", reason)

    segments = tuple(
        TranscriptSegment(
            start=float(s["start"]),
            duration=float(s.get("duration", 0.0)),
            text=str(s["text"]),
        )
        for s in data.get("segments", [])
        if s.get("text")
    )
    if not segments:
        return TranscriptFailure(video_id, "no_transcript", "relay returned empty segments")

    cached_label = " (cached)" if data.get("cached") else ""
    logger.info(
        "youtube_v2 relay video=%s lang=%s segments=%d%s",
        video_id, data.get("language", "?"), len(segments), cached_label,
    )
    return Transcript(
        video_id=video_id,
        language=data.get("language", "unknown"),
        source=TranscriptSource.AUTO_CAPTIONS,
        segments=segments,
    )


def fetch_transcript(
    video_id: str,
    *,
    preferred_langs: tuple[str, ...] = _PREFERRED_LANGS,
) -> Transcript | TranscriptFailure:
    """Fetch the best available transcript for a video.

    If YT_RELAY_URL is set, delegates to the transcript relay service running
    on a residential machine (bypasses Hetzner datacenter IP block).

    Otherwise fetches directly via youtube-transcript-api (residential IP or
    proxy required).
    """
    # YT_RELAY_URL may be a COMMA-SEPARATED pool of relays, each running on a
    # distinct residential IP (desktop, Trijya, a phone on mobile data, …). We
    # round-robin across them so the relays fetch in parallel — aggregate
    # throughput scales ~linearly with the number of healthy distinct-IP nodes.
    relay_pool = [u.strip() for u in os.getenv("YT_RELAY_URL", "").split(",") if u.strip()]
    if relay_pool:
        relay_url = relay_pool[next(_relay_rr) % len(relay_pool)]
        return _fetch_via_relay(video_id, relay_url)

    try:
        api = _make_api()
    except ImportError as exc:  # pragma: no cover - env guard
        return TranscriptFailure(video_id, "error", f"library missing: {exc}")

    try:
        listing = api.list(video_id)
    except Exception as exc:  # noqa: BLE001 - classify below
        return _classify_failure(video_id, exc)

    chosen = _choose_track(listing, preferred_langs)
    if chosen is None:
        logger.warning("youtube_v2 transcript video=%s reason=no_transcript", video_id)
        return TranscriptFailure(video_id, "no_transcript", "no caption tracks")

    track, source = chosen
    try:
        fetched = track.fetch()
    except Exception as exc:  # noqa: BLE001
        return _classify_failure(video_id, exc)

    raw = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else list(fetched)
    segments = tuple(
        TranscriptSegment(
            start=float(item["start"]),
            duration=float(item.get("duration", 0.0)),
            text=str(item["text"]),
        )
        for item in raw
        if item.get("text")
    )
    if not segments:
        return TranscriptFailure(video_id, "no_transcript", "empty after fetch")

    logger.info(
        "youtube_v2 transcript video=%s lang=%s source=%s segments=%d",
        video_id, track.language_code, source.value, len(segments),
    )
    return Transcript(
        video_id=video_id,
        language=track.language_code,
        source=source,
        segments=segments,
    )


def _choose_track(listing, preferred_langs: tuple[str, ...]):
    """Pick (track, source). Preferred language wins; manual beats auto for a
    given language; otherwise first available."""
    tracks = list(listing)
    if not tracks:
        return None

    def source_of(t) -> TranscriptSource:
        return (
            TranscriptSource.AUTO_CAPTIONS
            if getattr(t, "is_generated", False)
            else TranscriptSource.MANUAL_CAPTIONS
        )

    # 1) preferred language, manual first
    for lang in preferred_langs:
        same = [t for t in tracks if t.language_code == lang]
        if not same:
            continue
        same.sort(key=lambda t: getattr(t, "is_generated", False))  # manual (False) first
        return same[0], source_of(same[0])

    # 2) any track, manual first
    tracks.sort(key=lambda t: getattr(t, "is_generated", False))
    return tracks[0], source_of(tracks[0])


def _classify_failure(video_id: str, exc: Exception) -> TranscriptFailure:
    """Map a library exception to a typed, logged failure — never a bare None."""
    name = type(exc).__name__
    if any(m in name for m in _BLOCK_MARKERS):
        logger.warning("youtube_v2 transcript video=%s reason=ip_blocked", video_id)
        return TranscriptFailure(video_id, "ip_blocked", name)
    if any(m in name for m in _NO_TRANSCRIPT_MARKERS):
        logger.warning("youtube_v2 transcript video=%s reason=no_transcript", video_id)
        return TranscriptFailure(video_id, "no_transcript", name)
    if any(m in name for m in _UNPLAYABLE_MARKERS):
        logger.warning("youtube_v2 transcript video=%s reason=unplayable", video_id)
        return TranscriptFailure(video_id, "unplayable", name)
    logger.warning(
        "youtube_v2 transcript video=%s reason=error %s: %s",
        video_id, name, exc, exc_info=False,
    )
    return TranscriptFailure(video_id, "error", f"{name}: {exc}")
