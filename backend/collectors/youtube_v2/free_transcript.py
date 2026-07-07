"""Box-native YouTube transcript fetch — NO laptop relay, NO proxy, free.

The problem: YouTube's caption endpoints (`timedtext`) hard-block datacenter
IPs (Hetzner) with a "Sorry" anti-abuse wall, and a PO token does not change IP
reputation (verified exhaustively 2026-07-08). The residential relay works but
depends on a home machine staying up.

The way around it: **transcript-as-a-service providers do the residential fetch
on their own infra and return the text.** Our datacenter box calls the provider
over plain HTTPS and never touches YouTube's caption endpoint at all — so the
datacenter IP block is irrelevant. Verified working from the Hetzner box with no
relay/proxy: a 3-hour video returned ~150 KB of correct transcript in ~2 s.

Providers are an ordered pool (like the LLM key / relay pools) so a dead
provider fails over to the next. Add providers to `_PROVIDERS`; each returns
plain transcript text or None.

    from backend.collectors.youtube_v2.free_transcript import fetch_free_transcript
    text = fetch_free_transcript("mki7OWq05i8")
"""
from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger("youtube_v2")

_provider_rr = itertools.count()

# A transcript shorter than this is treated as an error page / empty, not text.
_MIN_CHARS = 80


@dataclass(frozen=True)
class FreeTranscript:
    """A transcript fetched via a free provider. Immutable."""

    video_id: str
    text: str
    provider: str
    chars: int
    truncated: bool = False   # provider signalled more content exists (hasMore)


def _looks_like_transcript(text: Optional[str]) -> bool:
    """Guard against HTML / bot-challenge / error bodies masquerading as text.

    (Learned the hard way: an Invidious 'are you a bot' page is >200 bytes and
    would pass a naive length check.)
    """
    if not text or len(text) < _MIN_CHARS:
        return False
    head = text.lstrip()[:200].lower()
    if head.startswith(("<!doctype", "<html")) or "just a moment" in head \
            or "not a bot" in head:
        return False
    return True


# ── providers ────────────────────────────────────────────────────────────────
# Each: (name, callable(video_id) -> (text, truncated) | None). Content is
# validated by the caller, so a provider only has to return its best-effort body.

def _kome(video_id: str) -> Optional[tuple[str, bool]]:
    """kome.ai — free, no auth. POST video_id, returns {transcript,hasMore,...}."""
    from curl_cffi.requests import Session

    r = Session().post(
        "https://kome.ai/api/transcript",
        json={"video_id": video_id, "format": True},
        timeout=45, impersonate="chrome",
    )
    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("application/json"):
        return None
    data = r.json()
    text = (data.get("transcript") or "").strip()
    return (text, bool(data.get("hasMore"))) if text else None


_PROVIDERS: list[tuple[str, Callable[[str], Optional[tuple[str, bool]]]]] = [
    ("kome.ai", _kome),
]


def fetch_free_transcript(video_id: str) -> Optional[FreeTranscript]:
    """Fetch a transcript via the free provider pool. Returns None if every
    provider fails or none has usable captions for the video.

    Rotates the pool start position (spreads load / avoids hammering one
    provider) and fails over on any error or non-transcript body.
    """
    if not video_id:
        return None
    n = len(_PROVIDERS)
    start = next(_provider_rr)
    for i in range(n):
        name, fn = _PROVIDERS[(start + i) % n]
        try:
            result = fn(video_id)
        except Exception as exc:  # a broken provider must not kill the chain
            logger.warning("free_transcript %s video=%s error=%s", name, video_id, exc)
            continue
        if result is None:
            continue
        text, truncated = result
        if not _looks_like_transcript(text):
            logger.warning("free_transcript %s video=%s returned non-transcript body",
                           name, video_id)
            continue
        logger.info("free_transcript %s video=%s chars=%d truncated=%s",
                    name, video_id, len(text), truncated)
        return FreeTranscript(video_id=video_id, text=text, provider=name,
                              chars=len(text), truncated=truncated)
    return None
