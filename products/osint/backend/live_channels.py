"""Live YouTube news-channel resolver.

YouTube live video IDs rotate every few hours and channels go on/off air, so a
hardcoded list goes stale fast. This resolves each candidate channel's CURRENT live
video by fetching its /live page, and returns only the ones that are genuinely live
+ embeddable right now (capped at 6) — no dead tiles.

IP hygiene: results are cached per (scope, state) for 25 minutes, so the Hetzner host
makes at most a handful of lightweight HTML GETs per cycle (far lighter than yt-dlp).
This does NOT touch the clip-transcript pipeline's yt-dlp path.
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import httpx

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_HEADERS = {"user-agent": _UA, "accept-language": "en-US,en;q=0.9"}
_VID_RE = re.compile(r'"videoId":"([\w-]{11})"')

MAX_TILES = 6
_TTL_SECONDS = 1500  # 25 min
_FETCH_TIMEOUT = 6.0

# Candidate pools — channelId source-verified by resolving each handle (2026-06-04).
# Tuple is (name, channelId, always_on). always_on channels run a single 24/7 stream
# (never off-air), so live_stream?channel= is a reliable fallback when the scrape can't
# confirm the live videoId. Multi-live / intermittent channels are surfaced ONLY when we
# resolve a confirmed live videoId (else they'd show "Video unavailable").
GLOBAL_POOL = [
    ("Al Jazeera English", "UCfiwzLy-8yKzIbsmZTzxDgw", True),
    ("DW News", "UCbbS1GE942k3UVqpLklyhIA", True),
    ("France 24 English", "UCCCPCZNChQdGa9EkATeye4g", True),
    ("WION", "UCWEIPvoxRwn6llPOIn555rQ", True),
    ("Sky News", "UCkFclpi8U9VJjfxLYoms7Aw", True),
    ("Al Jazeera Arabic", "UCBa659QWEk1AI4Tg--mrJ2A", True),
]

NATIONAL_POOL = [
    ("NDTV", "UCXBD5iG5cr4ZYZ99K-fmDHg", False),
    ("India Today", "UCYPvAwZP8pZhSMW8qs7cVCw", False),
    ("Republic World", "UChIuMQsOdbrc4Evj_raoDZA", False),
    ("WION", "UCWEIPvoxRwn6llPOIn555rQ", True),
]

# Regional Telugu channels (cover both AP + TG); whichever is live gets surfaced.
REGIONAL_POOL = {
    "AP": [
        ("TV9 Telugu", "UCfaww9Q8C_-EaM0sXI8o-fA", False),
        ("ABN Telugu", "UC_2irx_BQR7RsBKmUV9fePQ", False),
        ("Sakshi TV", "UCQ_FATLW83q-4xJ2fsi8qAw", False),
        ("ETV Andhra Pradesh", "UCSs9H1cyB3OHdy8wkit8ZKg", False),
        ("10TV", "UCBF2w5CGS8d0YLygY0nlnXQ", False),
        ("TV5 News", "UCAR3h_9fLV82N2FH4yEDnpg", False),
        ("Mahaa News", "UCf40zfa4GGOC9s8yoQhGZGg", False),
    ],
    "TG": [
        ("V6 News", "UC239yTgdQbce3omeOjCt8_A", False),
        ("TV9 Telugu", "UCfaww9Q8C_-EaM0sXI8o-fA", False),
        ("Mahaa News", "UCf40zfa4GGOC9s8yoQhGZGg", False),
        ("ABN Telugu", "UC_2irx_BQR7RsBKmUV9fePQ", False),
        ("Sakshi TV", "UCQ_FATLW83q-4xJ2fsi8qAw", False),
        ("10TV", "UCBF2w5CGS8d0YLygY0nlnXQ", False),
    ],
}

# (scope, state) -> (monotonic_ts, list[dict])
_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


async def _resolve_one(client: httpx.AsyncClient, name: str, cid: str) -> dict[str, Any] | None:
    """Return {name, id, live} if the channel is live + embeddable, else None."""
    try:
        r = await client.get(f"https://www.youtube.com/channel/{cid}/live", headers=_HEADERS,
                             timeout=_FETCH_TIMEOUT, follow_redirects=True)
        t = r.text
        m = _VID_RE.search(t)
        is_live = "hlsManifestUrl" in t
        embeddable = '"playableInEmbed":true' in t
        if m and is_live and embeddable:
            return {"name": name, "id": cid, "live": m.group(1)}
    except (httpx.HTTPError, asyncio.TimeoutError):
        return None
    return None


def _pool_for(scope: str, state: str) -> list[tuple[str, str, bool]]:
    if scope == "global":
        return GLOBAL_POOL
    return NATIONAL_POOL[:3] + REGIONAL_POOL.get(state, REGIONAL_POOL["AP"])


async def resolve_channels(scope: str, state: str) -> list[dict[str, Any]]:
    """Live channels for (scope, state), capped at MAX_TILES. Cached 25 min.

    A channel is surfaced if we resolved a confirmed live videoId; an always_on
    channel is also surfaced (via live_stream fallback, no videoId) when the scrape
    can't confirm — these never go off-air, so the fallback is safe.
    """
    key = f"{scope}:{state}"
    hit = _CACHE.get(key)
    if hit and (time.monotonic() - hit[0]) < _TTL_SECONDS:
        return hit[1]

    pool = _pool_for(scope, state)
    async with httpx.AsyncClient() as client:
        resolved = await asyncio.gather(*[_resolve_one(client, n, c) for n, c, _ in pool])

    live: list[dict[str, Any]] = []
    for (name, cid, always_on), res in zip(pool, resolved):
        if res:
            live.append(res)
        elif always_on:
            live.append({"name": name, "id": cid})  # live_stream?channel= fallback
        if len(live) >= MAX_TILES:
            break

    # Keep a previous non-empty result if this cycle resolved nothing (transient).
    if not live and hit:
        return hit[1]
    _CACHE[key] = (time.monotonic(), live)
    return live
