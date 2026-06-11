"""
Safe IP-block diagnostic — NO yt-dlp, NO writes, NO audio download.

Tests each YouTube access path independently and reports block status.
Safe to run from Hetzner: single requests, throttled, read-only.

Run inside the rig-backend container:
    docker exec rig-backend python -m backend.tests._probe_ip_block

Or locally (from repo root):
    python -m backend.tests._probe_ip_block
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from typing import Literal

import httpx

# ── Config ────────────────────────────────────────────────────────────────────

# A single well-known Telugu news channel (V6 News) — used only for probing.
# We grab its latest video ID from RSS, then test the transcript endpoint.
PROBE_CHANNEL_ID = "UCDCMjD1XIAsCZsYHNMGVcog"  # V6 News Telugu

# Minimum sleep between probes — keeps us from looking like a scraper
PROBE_DELAY_S = 5.0

Status = Literal["ok", "blocked", "error", "skipped"]


@dataclass
class ProbeResult:
    path: str
    status: Status
    detail: str = ""
    latency_ms: int = 0
    extra: dict = field(default_factory=dict)


results: list[ProbeResult] = []


def _log(msg: str) -> None:
    print(f"  {msg}", flush=True)


# ── Probe 1: RSS feed ─────────────────────────────────────────────────────────

async def probe_rss() -> str | None:
    """Fetch the channel RSS feed. Returns the latest video_id or None."""
    print("\n[1/4] RSS Atom feed (safe, unauthenticated)")
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={PROBE_CHANNEL_ID}"
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        ms = int((time.monotonic() - t0) * 1000)
        if resp.status_code == 200 and b"<entry>" in resp.content:
            import xml.etree.ElementTree as ET
            ns = {"yt": "http://www.youtube.com/xml/schemas/2015"}
            root = ET.fromstring(resp.text)
            entry = root.find(".//{http://www.w3.org/2005/Atom}entry")
            vid_id = None
            if entry is not None:
                vid_el = entry.find("yt:videoId", ns)
                vid_id = vid_el.text if vid_el is not None else None
            results.append(ProbeResult("rss", "ok", f"HTTP {resp.status_code}", ms))
            _log(f"OK  {ms}ms  latest_video_id={vid_id}")
            return vid_id
        else:
            results.append(ProbeResult("rss", "blocked", f"HTTP {resp.status_code}", ms))
            _log(f"BLOCKED  {ms}ms  HTTP {resp.status_code}")
            return None
    except Exception as exc:
        results.append(ProbeResult("rss", "error", str(exc)))
        _log(f"ERROR  {exc}")
        return None


# ── Probe 2: transcript-api (caption timed-text endpoint) ────────────────────

async def probe_transcript_api(video_id: str) -> None:
    """One transcript fetch via youtube-transcript-api. No cookies, no proxy."""
    print(f"\n[2/4] youtube-transcript-api  video={video_id}  (no cookies)")
    _log(f"sleeping {PROBE_DELAY_S}s before request …")
    await asyncio.sleep(PROBE_DELAY_S)
    t0 = time.monotonic()
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "te", "hi"])
        ms = int((time.monotonic() - t0) * 1000)
        snippet = (transcript[0].get("text", "") if transcript else "")[:80]
        results.append(ProbeResult(
            "transcript_api_plain", "ok",
            f"{len(transcript)} segments", ms,
            {"snippet": snippet},
        ))
        _log(f"OK  {ms}ms  {len(transcript)} segs  snippet={snippet!r}")
    except Exception as exc:
        ms = int((time.monotonic() - t0) * 1000)
        name = type(exc).__name__
        is_block = any(k in name for k in ("Blocked", "IpBlocked", "RequestBlocked"))
        status: Status = "blocked" if is_block else "error"
        results.append(ProbeResult("transcript_api_plain", status, f"{name}: {exc}", ms))
        _log(f"{'BLOCKED' if is_block else 'ERROR'}  {ms}ms  {name}: {exc}")


# ── Probe 3: transcript-api with cookies ─────────────────────────────────────

async def probe_transcript_api_cookies(video_id: str) -> None:
    """Same endpoint but with YOUTUBE_COOKIES_PATH if configured."""
    cookies_path = os.getenv("YOUTUBE_COOKIES_PATH", "").strip()
    if not cookies_path or not os.path.exists(cookies_path):
        results.append(ProbeResult("transcript_api_cookies", "skipped", "YOUTUBE_COOKIES_PATH not set"))
        print(f"\n[3/4] transcript-api + cookies — SKIPPED (YOUTUBE_COOKIES_PATH not set)")
        return

    print(f"\n[3/4] youtube-transcript-api + cookies  video={video_id}")
    _log(f"sleeping {PROBE_DELAY_S}s before request …")
    await asyncio.sleep(PROBE_DELAY_S)
    t0 = time.monotonic()
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        # Pass cookies file path — supported in youtube-transcript-api ≥0.6
        api = YouTubeTranscriptApi(cookies=cookies_path)
        transcript = api.get_transcript(video_id, languages=["en", "te", "hi"])
        ms = int((time.monotonic() - t0) * 1000)
        results.append(ProbeResult(
            "transcript_api_cookies", "ok",
            f"{len(transcript)} segments", ms,
        ))
        _log(f"OK  {ms}ms  {len(transcript)} segs")
    except Exception as exc:
        ms = int((time.monotonic() - t0) * 1000)
        name = type(exc).__name__
        is_block = any(k in name for k in ("Blocked", "IpBlocked", "RequestBlocked"))
        status = "blocked" if is_block else "error"
        results.append(ProbeResult("transcript_api_cookies", status, f"{name}: {exc}", ms))
        _log(f"{'BLOCKED' if is_block else 'ERROR'}  {ms}ms  {name}: {exc}")


# ── Probe 4: timed-text HTTP endpoint directly ───────────────────────────────

async def probe_timedtext_direct(video_id: str) -> None:
    """
    Hit YouTube's internal timed-text endpoint directly with httpx.
    This reveals whether it's an IP block (HTTP 403/429) vs a bot-check
    (redirect to consent page) vs fully open.

    We fetch the video page first to extract the timedtext URL — this is
    the same path youtube-transcript-api takes, but we do it manually so
    we can see the exact HTTP status at each hop.
    """
    print(f"\n[4/4] timed-text HTTP probe (manual)  video={video_id}")
    _log(f"sleeping {PROBE_DELAY_S}s before request …")
    await asyncio.sleep(PROBE_DELAY_S)
    t0 = time.monotonic()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(watch_url, headers=headers)
        ms = int((time.monotonic() - t0) * 1000)
        body = resp.text

        # Detect consent wall
        if "consent.youtube.com" in str(resp.url) or "before you continue" in body.lower():
            results.append(ProbeResult("timedtext_direct", "blocked", "consent wall redirect", ms))
            _log(f"BLOCKED (consent wall)  {ms}ms  final_url={resp.url}")
            return

        # Detect bot check page
        if "sign in to confirm" in body.lower() or "www.google.com/recaptcha" in body.lower():
            results.append(ProbeResult("timedtext_direct", "blocked", "bot-check page", ms))
            _log(f"BLOCKED (bot check)  {ms}ms")
            return

        # Look for timedtext URL in the page JS
        import re
        tt_match = re.search(r'"(https://www\.youtube\.com/api/timedtext[^"]+)"', body)
        if not resp.ok:
            results.append(ProbeResult("timedtext_direct", "blocked", f"HTTP {resp.status_code}", ms))
            _log(f"BLOCKED  HTTP {resp.status_code}  {ms}ms")
            return

        if tt_match:
            tt_url = tt_match.group(1).replace("\\u0026", "&")
            results.append(ProbeResult(
                "timedtext_direct", "ok",
                f"watch page OK, timedtext URL found", ms,
                {"timedtext_url_prefix": tt_url[:80]},
            ))
            _log(f"OK  {ms}ms  watch page loaded, timedtext URL extracted")
        else:
            # Page loaded but no captions (live stream, members-only, no captions)
            has_captions = '"captions"' in body or 'captionTracks' in body
            results.append(ProbeResult(
                "timedtext_direct", "ok",
                f"watch page OK, captions={'maybe' if has_captions else 'none found'}", ms,
            ))
            _log(f"OK  {ms}ms  watch page loaded  captions={'maybe' if has_captions else 'none'}")
    except Exception as exc:
        ms = int((time.monotonic() - t0) * 1000)
        results.append(ProbeResult("timedtext_direct", "error", str(exc), ms))
        _log(f"ERROR  {ms}ms  {exc}")


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary() -> None:
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for r in results:
        icon = {"ok": "✓", "blocked": "✗", "error": "!", "skipped": "-"}[r.status]
        lat = f"{r.latency_ms}ms" if r.latency_ms else "—"
        print(f"  {icon} {r.path:<35} {r.status:<8} {lat:<8} {r.detail}")

    blocked = [r for r in results if r.status == "blocked"]
    errors  = [r for r in results if r.status == "error"]
    ok      = [r for r in results if r.status == "ok"]

    print()
    if not blocked and not errors:
        print("  ► This IP is NOT blocked. All paths reachable.")
    elif blocked and not ok:
        print("  ► This IP appears FULLY BLOCKED by YouTube.")
    elif blocked:
        print(f"  ► PARTIAL block: {len(blocked)} path(s) blocked, {len(ok)} ok.")
        print("    Blocked paths:", [r.path for r in blocked])
    else:
        print(f"  ► Errors on {len(errors)} path(s) — likely library/config issue, not IP block.")

    # Machine-readable dump
    out_path = "/tmp/yt_ip_probe.json"
    try:
        with open(out_path, "w") as f:
            json.dump(
                [{"path": r.path, "status": r.status, "detail": r.detail,
                  "latency_ms": r.latency_ms, "extra": r.extra}
                 for r in results],
                f, indent=2,
            )
        print(f"\n  Results written to {out_path}")
    except Exception:
        pass


# ── Entry ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    print("YouTube IP-block diagnostic")
    print(f"Channel: {PROBE_CHANNEL_ID}  (V6 News Telugu)")
    print(f"Proxy env: {os.getenv('YOUTUBE_PROXY_URL', '(none)')}")
    print(f"Cookies env: {os.getenv('YOUTUBE_COOKIES_PATH', '(none)')}")
    print()

    video_id = await probe_rss()

    if video_id:
        await probe_transcript_api(video_id)
        await probe_transcript_api_cookies(video_id)
        await probe_timedtext_direct(video_id)
    else:
        print("\n  RSS returned no video_id — skipping transcript probes.")
        print("  If RSS itself was blocked, the IP is severely restricted.")

    print_summary()


if __name__ == "__main__":
    asyncio.run(main())
