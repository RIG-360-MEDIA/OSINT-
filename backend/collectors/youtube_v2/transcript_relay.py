"""
Transcript Relay Service — runs on a residential machine (laptop / TRIJYA-7).
Hetzner calls this instead of touching YouTube directly.

Fetch engine: **yt-dlp + authenticated cookies** (was youtube-transcript-api).
yt-dlp goes through the innertube player flow (mimics a real browser) and, with a
logged-in cookie jar, requests are treated as an authenticated user — YouTube's
highest-trust tier. The yt-dlp wiki documents the authenticated ceiling at
~2000 videos/hr vs ~300/hr anonymous. We stay FAR under that.

Safeguards built-in:
  - Token-bucket rate limiter    : 1 YouTube call per 7s (honours the wiki's
                                   5-10s spacing guidance; ~8.5/min ceiling)
  - Exponential backoff          : 429/bot-wall → 10s, 20s, 40s, 80s
  - Circuit breaker              : 5 consecutive failures → 5-min pause
  - Response cache               : 30-min TTL (same video never re-fetched)
  - Request serialisation        : one YouTube fetch at a time, no burst

SAFETY:
  - Use a THROWAWAY Google account for the cookies, never a personal one —
    accounts used for automation can be flagged/banned.
  - Do NOT keep a YouTube tab open in the browser the cookies were exported
    from; YouTube rotates session cookies on open tabs and the export goes stale.

Usage:
    pip install flask yt-dlp
    set YT_COOKIES=C:\\path\\to\\cookies.txt      # optional but strongly recommended
    python transcript_relay.py                    # listens on :8888

Hetzner side:
    YT_RELAY_URL=http://<this-machine-tailscale-ip>:8888
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

from flask import Flask, jsonify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s relay %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("relay")

app = Flask(__name__)

# ── config ────────────────────────────────────────────────────────────────────
# 1 call per 7s honours the yt-dlp wiki's 5-10s spacing guidance and keeps the
# per-IP rate (~8.5/min ceiling) an order of magnitude under the ~2000/hr
# authenticated ban threshold. The real sustained rate is set by Hetzner's Beat
# cadence, which is lower still; this is just the hard burst ceiling.
RATE_INTERVAL        = float(os.getenv("RELAY_RATE_INTERVAL", "7.0"))

CB_FAILURE_THRESHOLD = 5      # consecutive failures before opening circuit
CB_RESET_SECS        = 300    # 5 minutes cool-down before circuit closes

CACHE_TTL_SECS       = 1800   # cache transcripts for 30 minutes

MAX_RETRIES          = 4      # per-request retry count
BACKOFF_BASE_SECS    = 10     # doubles each retry: 10, 20, 40, 80

# Preferred caption languages, in order. We accept the source language even if
# non-English — extraction translates downstream. Auto-generated is fine.
PREFERRED_LANGS      = ("en", "en-orig", "en-US", "en-GB", "te", "hi", "kn", "ta", "ur")

# Path to a Netscape-format cookies.txt for a THROWAWAY logged-in YouTube account.
COOKIE_FILE          = os.getenv("YT_COOKIES", "").strip()

# ── rate limiter (token bucket) ───────────────────────────────────────────────
_rate_lock        = threading.Lock()
_last_request_at  = 0.0


def _wait_for_token() -> None:
    global _last_request_at
    with _rate_lock:
        now   = time.monotonic()
        since = now - _last_request_at
        if since < RATE_INTERVAL:
            wait = RATE_INTERVAL - since
            logger.info("rate limiter: waiting %.1fs before next YouTube call", wait)
            time.sleep(wait)
        _last_request_at = time.monotonic()


# ── circuit breaker ───────────────────────────────────────────────────────────
_cb_lock        = threading.Lock()
_cb_failures    = 0
_cb_open_until  = 0.0


def _cb_check() -> tuple[bool, float]:
    global _cb_open_until
    with _cb_lock:
        if _cb_open_until == 0.0:
            return False, 0.0
        remaining = _cb_open_until - time.time()
        if remaining <= 0:
            _cb_open_until = 0.0
            logger.info("circuit breaker: half-open — trying again")
            return False, 0.0
        return True, remaining


def _cb_success() -> None:
    global _cb_failures, _cb_open_until
    with _cb_lock:
        if _cb_failures > 0:
            logger.info("circuit breaker: success, resetting failure count")
        _cb_failures   = 0
        _cb_open_until = 0.0


def _cb_failure() -> None:
    global _cb_failures, _cb_open_until
    with _cb_lock:
        _cb_failures += 1
        logger.warning("circuit breaker: failure %d/%d", _cb_failures, CB_FAILURE_THRESHOLD)
        if _cb_failures >= CB_FAILURE_THRESHOLD:
            _cb_open_until = time.time() + CB_RESET_SECS
            logger.warning(
                "circuit breaker: OPEN — blocking all requests for %ds", CB_RESET_SECS
            )


# ── response cache ────────────────────────────────────────────────────────────
_cache_lock  = threading.Lock()
_cache: dict[str, tuple[float, Any]] = {}


def _cache_get(video_id: str) -> Any | None:
    with _cache_lock:
        entry = _cache.get(video_id)
        if entry and time.time() - entry[0] < CACHE_TTL_SECS:
            return entry[1]
        if entry:
            del _cache[video_id]
    return None


def _cache_put(video_id: str, data: Any) -> None:
    with _cache_lock:
        _cache[video_id] = (time.time(), data)
        logger.info("cache: stored video=%s (total cached: %d)", video_id, len(_cache))


# ── yt-dlp fetch ──────────────────────────────────────────────────────────────
_fetch_lock = threading.Lock()

# Error-message markers (yt-dlp raises DownloadError/HTTPError with these in the text)
_BLOCK_MARKERS    = ("429", "Too Many Requests", "Sign in to confirm",
                     "not a bot", "blocked", "HTTP Error 403")
_NO_CAPTION_MARK  = ("no_transcript",)
_UNPLAYABLE_MARK  = ("unavailable", "private", "removed", "members-only",
                     "members only", "age-restricted", "this video is not available")


def _ydl_opts() -> dict:
    opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        # return the extractor's info (incl. caption tracks) WITHOUT running video
        # format selection, which errors when only image formats exist (no PO token)
        "ignore_no_formats_error": True,
        "extractor_args": {"youtube": {"player_client": ["web"]}},
    }
    if COOKIE_FILE and os.path.exists(COOKIE_FILE):
        opts["cookiefile"] = COOKIE_FILE
    return opts


def _pick_track(manual: dict, auto: dict) -> tuple[str | None, list | None, bool]:
    """Preferred-language manual track wins, then preferred auto, then anything."""
    for lang in PREFERRED_LANGS:
        if lang in manual:
            return lang, manual[lang], False
    for lang in PREFERRED_LANGS:
        if lang in auto:
            return lang, auto[lang], True
    if manual:
        k = next(iter(manual)); return k, manual[k], False
    if auto:
        k = next(iter(auto)); return k, auto[k], True
    return None, None, False


def _parse_json3(raw: bytes) -> list[dict]:
    data = json.loads(raw)
    segs: list[dict] = []
    for e in data.get("events", []):
        if "segs" not in e:
            continue
        text = "".join(s.get("utf8", "") for s in e["segs"]).strip()
        if text:
            segs.append({
                "start":    e.get("tStartMs", 0) / 1000.0,
                "duration": e.get("dDurationMs", 0) / 1000.0,
                "text":     text,
            })
    return segs


def _do_fetch(video_id: str) -> dict:
    """Single attempt via yt-dlp: extract caption tracks → fetch json3 → segments."""
    from yt_dlp import YoutubeDL

    _wait_for_token()
    url = f"https://www.youtube.com/watch?v={video_id}"
    with YoutubeDL(_ydl_opts()) as ydl:
        info = ydl.extract_info(url, download=False, process=False)
        manual = info.get("subtitles") or {}
        auto   = info.get("automatic_captions") or {}
        lang, tracks, is_auto = _pick_track(manual, auto)
        if not lang or not tracks:
            return {"ok": False, "reason": "no_transcript"}

        track = next((t for t in tracks if t.get("ext") == "json3"), tracks[0])
        raw = ydl.urlopen(track["url"]).read()

    segs = _parse_json3(raw)
    if not segs:
        return {"ok": False, "reason": "empty_transcript"}

    return {"ok": True, "video_id": video_id, "language": lang, "segments": segs}


def _classify(exc: Exception) -> str:
    msg = f"{type(exc).__name__}: {exc}"
    if any(m.lower() in msg.lower() for m in _BLOCK_MARKERS):
        return "ip_blocked"
    if any(m.lower() in msg.lower() for m in _UNPLAYABLE_MARK):
        return "unplayable"
    if "subtitle" in msg.lower() or "caption" in msg.lower():
        return "no_transcript"
    return f"error:{type(exc).__name__}"


def _fetch_with_safeguards(video_id: str) -> dict:
    """Fetch with retry, backoff, and circuit breaker."""
    last_err = "unknown"
    for attempt in range(MAX_RETRIES):
        is_open, remaining = _cb_check()
        if is_open:
            logger.warning("circuit open: rejecting video=%s, retry in %ds", video_id, int(remaining))
            return {"ok": False, "reason": "circuit_open", "retry_after": int(remaining)}

        try:
            result = _do_fetch(video_id)
            # A clean "no captions" answer is terminal, not a failure.
            if not result.get("ok") and result.get("reason") in ("no_transcript", "empty_transcript"):
                _cb_success()
                return result
            _cb_success()
            return result
        except Exception as exc:  # noqa: BLE001 - classify below
            reason = _classify(exc)
            last_err = reason

            if reason in ("unplayable",):
                _cb_success()  # terminal, not an IP problem
                logger.info("video=%s terminal: %s", video_id, reason)
                return {"ok": False, "reason": reason}
            if reason == "no_transcript":
                _cb_success()
                return {"ok": False, "reason": "no_transcript"}

            _cb_failure()
            if reason == "ip_blocked":
                backoff = BACKOFF_BASE_SECS * (2 ** attempt)
                logger.warning("video=%s attempt %d/%d: %s — backing off %ds",
                               video_id, attempt + 1, MAX_RETRIES, reason, backoff)
                time.sleep(backoff)
            else:
                logger.error("video=%s unexpected: %s", video_id, reason)
                return {"ok": False, "reason": reason}

    return {"ok": False, "reason": f"max_retries_exceeded:{last_err}"}


# ── HTTP endpoints ────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    is_open, remaining = _cb_check()
    with _cache_lock:
        cache_size = len(_cache)
    with _cb_lock:
        failures = _cb_failures
    return jsonify({
        "status":        "degraded" if is_open else "ok",
        "circuit":       "open" if is_open else "closed",
        "retry_after":   int(remaining) if is_open else 0,
        "cb_failures":   failures,
        "cb_threshold":  CB_FAILURE_THRESHOLD,
        "cache_entries": cache_size,
        "engine":        "yt-dlp",
        "authenticated": bool(COOKIE_FILE and os.path.exists(COOKIE_FILE)),
        "rate_interval": RATE_INTERVAL,
    })


@app.get("/fetch/<video_id>")
def fetch(video_id: str):
    cached = _cache_get(video_id)
    if cached:
        logger.info("cache hit video=%s segs=%d", video_id, len(cached.get("segments", [])))
        return jsonify({**cached, "cached": True})

    is_open, remaining = _cb_check()
    if is_open:
        return jsonify({"ok": False, "reason": "circuit_open", "retry_after": int(remaining)}), 503

    with _fetch_lock:
        cached = _cache_get(video_id)
        if cached:
            return jsonify({**cached, "cached": True})
        logger.info("fetching video=%s", video_id)
        result = _fetch_with_safeguards(video_id)

    if result.get("ok"):
        _cache_put(video_id, result)
        return jsonify(result), 200

    reason = result.get("reason", "")
    status = 503 if "circuit_open" in reason else 502
    return jsonify(result), status


# ── entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("RELAY_PORT", "8888"))
    authed = bool(COOKIE_FILE and os.path.exists(COOKIE_FILE))
    logger.info("=" * 60)
    logger.info("transcript relay starting on 0.0.0.0:%d", port)
    logger.info("engine      : yt-dlp")
    logger.info("cookies     : %s", COOKIE_FILE if authed else "NONE (anonymous — much lower rate)")
    logger.info("rate        : 1 call / %.0fs (honours 5-10s wiki guidance)", RATE_INTERVAL)
    logger.info("backoff     : %ds base, doubles per retry (max %d retries)", BACKOFF_BASE_SECS, MAX_RETRIES)
    logger.info("circuit     : opens after %d failures, resets after %ds", CB_FAILURE_THRESHOLD, CB_RESET_SECS)
    logger.info("=" * 60)
    app.run(host="0.0.0.0", port=port, threaded=True)
