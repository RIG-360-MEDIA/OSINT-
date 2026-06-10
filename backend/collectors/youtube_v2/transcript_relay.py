"""
Transcript Relay Service — runs on a residential machine (laptop / TRIJYA-7).
Hetzner calls this instead of touching YouTube directly.

Safeguards built-in:
  - Token-bucket rate limiter    : max 15 req/min to YouTube (1 per 4s)
  - Exponential backoff          : 429/IpBlocked → 10s, 20s, 40s, 80s
  - Circuit breaker              : 5 consecutive failures → 5-min pause
  - Response cache               : 30-min TTL (same video never re-fetched)
  - Request serialisation        : one YouTube fetch at a time, no burst

Usage:
    pip install flask youtube-transcript-api
    python transcript_relay.py

    # Optional: also configure a backup Webshare proxy
    set WEBSHARE_USER=xxx
    set WEBSHARE_PASS=yyy
    python transcript_relay.py

Hetzner side:
    YT_RELAY_URL=http://<this-machine-tailscale-ip>:8888
"""
from __future__ import annotations

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
RATE_LIMIT_PER_MIN  = 15      # max YouTube requests per minute
RATE_INTERVAL       = 60.0 / RATE_LIMIT_PER_MIN   # 4 seconds between requests

CB_FAILURE_THRESHOLD = 5      # consecutive failures before opening circuit
CB_RESET_SECS        = 300    # 5 minutes cool-down before circuit closes

CACHE_TTL_SECS       = 1800   # cache transcripts for 30 minutes

MAX_RETRIES          = 4      # per-request retry count
BACKOFF_BASE_SECS    = 10     # doubles each retry: 10, 20, 40, 80

PREFERRED_LANGS      = ["te", "hi", "en"]

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


# ── youtube api factory ───────────────────────────────────────────────────────
def _make_api():
    from youtube_transcript_api import YouTubeTranscriptApi

    webshare_user = os.getenv("WEBSHARE_USER", "").strip()
    webshare_pass = os.getenv("WEBSHARE_PASS", "").strip()
    yt_proxy      = os.getenv("YT_PROXY", "").strip()

    if webshare_user and webshare_pass:
        from youtube_transcript_api.proxies import WebshareProxyConfig
        logger.debug("using Webshare proxy backup")
        return YouTubeTranscriptApi(
            proxy_config=WebshareProxyConfig(
                proxy_username=webshare_user,
                proxy_password=webshare_pass,
            )
        )
    if yt_proxy:
        from youtube_transcript_api.proxies import GenericProxyConfig
        return YouTubeTranscriptApi(
            proxy_config=GenericProxyConfig(http_url=yt_proxy, https_url=yt_proxy)
        )
    return YouTubeTranscriptApi()


# ── fetch serialisation lock ──────────────────────────────────────────────────
_fetch_lock = threading.Lock()

_RETRYABLE_ERRORS = ("IpBlocked", "RequestBlocked", "TooManyRequests")
_FATAL_ERRORS     = ("NoTranscriptFound", "TranscriptsDisabled", "VideoUnplayable", "VideoUnavailable")


def _do_fetch(video_id: str) -> dict:
    """Single attempt: list tracks → pick best → fetch segments."""
    api  = _make_api()
    _wait_for_token()

    listing = api.list(video_id)
    tracks  = list(listing)
    if not tracks:
        return {"ok": False, "reason": "no_transcript"}

    chosen = None
    for lang in PREFERRED_LANGS:
        match = [t for t in tracks if t.language_code == lang]
        if match:
            match.sort(key=lambda t: getattr(t, "is_generated", False))
            chosen = match[0]
            break
    if chosen is None:
        tracks.sort(key=lambda t: getattr(t, "is_generated", False))
        chosen = tracks[0]

    fetched = chosen.fetch()
    raw = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else list(fetched)
    segs = [
        {
            "start":    float(s["start"]),
            "duration": float(s.get("duration", 0.0)),
            "text":     str(s["text"]),
        }
        for s in raw if s.get("text")
    ]
    if not segs:
        return {"ok": False, "reason": "empty_transcript"}

    return {
        "ok":       True,
        "video_id": video_id,
        "language": chosen.language_code,
        "segments": segs,
    }


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
            _cb_success()
            return result

        except Exception as exc:
            name = type(exc).__name__
            last_err = name

            if any(m in name for m in _FATAL_ERRORS):
                _cb_success()
                logger.info("video=%s terminal failure: %s", video_id, name)
                return {"ok": False, "reason": name}

            _cb_failure()

            if any(m in name for m in _RETRYABLE_ERRORS):
                backoff = BACKOFF_BASE_SECS * (2 ** attempt)
                logger.warning(
                    "video=%s attempt %d/%d: %s — backing off %ds",
                    video_id, attempt + 1, MAX_RETRIES, name, backoff,
                )
                time.sleep(backoff)
            else:
                logger.error("video=%s unexpected: %s: %s", video_id, name, exc)
                return {"ok": False, "reason": f"error:{name}"}

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
        "rate_limit":    f"{RATE_LIMIT_PER_MIN}/min",
    })


@app.get("/fetch/<video_id>")
def fetch(video_id: str):
    # 1. cache hit — return immediately, no rate limit consumed
    cached = _cache_get(video_id)
    if cached:
        logger.info("cache hit video=%s segs=%d", video_id, len(cached.get("segments", [])))
        return jsonify({**cached, "cached": True})

    # 2. circuit open — reject fast
    is_open, remaining = _cb_check()
    if is_open:
        return jsonify({"ok": False, "reason": "circuit_open", "retry_after": int(remaining)}), 503

    # 3. serialise: one YouTube call at a time
    with _fetch_lock:
        cached = _cache_get(video_id)     # double-check after acquiring lock
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
    logger.info("=" * 60)
    logger.info("transcript relay starting on 0.0.0.0:%d", port)
    logger.info("rate limit  : %d req/min (1 per %.0fs)", RATE_LIMIT_PER_MIN, RATE_INTERVAL)
    logger.info("backoff     : %ds base, doubles per retry (max %d retries)", BACKOFF_BASE_SECS, MAX_RETRIES)
    logger.info("circuit     : opens after %d failures, resets after %ds", CB_FAILURE_THRESHOLD, CB_RESET_SECS)
    logger.info("cache TTL   : %ds", CACHE_TTL_SECS)
    logger.info("=" * 60)
    app.run(host="0.0.0.0", port=port, threaded=True)
