"""
Instagram Relay Service — runs on a residential machine (this laptop).
Hetzner calls this instead of touching Instagram directly.

Instagram blocks datacenter IPs (Hetzner) from their GraphQL endpoints.
A residential IP + valid session has no such restriction.

Fetch engine: raw Instagram mobile API (`i.instagram.com/api/v1/`).
NOT instaloader — that library uses a stale doc_id and is broken as of mid-2025.

Endpoints used:
  GET https://www.instagram.com/api/v1/users/web_profile_info/?username={u}
      → returns user id (needed for feed)
  GET https://i.instagram.com/api/v1/feed/user/{user_id}/?count={n}
      → returns paginated posts with like_count, comments etc.

Safeguards:
  - Token-bucket rate limiter : 1 Instagram API call per 5s
  - Exponential backoff       : 401/403/429 → 10s, 20s, 40s, 80s
  - Circuit breaker           : 5 consecutive failures → 5-min pause
  - Response cache            : 10-min TTL per username
  - Thread lock               : serialises all Instagram calls

Usage:
    pip install flask requests
    set INSTA_SESSIONID=<sessionid cookie value>
    python instagram_relay.py          # listens on :8890

Hetzner side:
    INSTAGRAM_RELAY_URL=http://<this-machine-tailscale-ip>:8890
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from datetime import timezone, datetime
from typing import Any

from flask import Flask, jsonify, request
import requests as _req

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s relay %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("instagram_relay")

app = Flask(__name__)

# ── config ────────────────────────────────────────────────────────────────────

RATE_INTERVAL        = float(os.getenv("RELAY_RATE_INTERVAL", "5.0"))
CB_FAILURE_THRESHOLD = 5
CB_RESET_AFTER       = 300     # seconds
CACHE_TTL            = 600     # seconds
PORT                 = int(os.getenv("INSTAGRAM_RELAY_PORT", "8890"))

# Read session ID from env; fall back to env file pattern used by YouTube relay
_SESSIONID = os.getenv("INSTA_SESSIONID", "")

# ── fake device fingerprint (keeps mobile API happy) ──────────────────────────

_DEVICE_ID  = str(uuid.uuid4())
_ANDROID_ID = "android-" + uuid.uuid4().hex[:16]

_WEB_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "X-IG-App-ID": "936619743392459",
    "Accept-Language": "en-US,en;q=0.9",
}

_MOBILE_HEADERS = {
    "User-Agent": (
        "Instagram 325.0.0.35.90 Android (34/14; 420dpi; 1080x2400; "
        "samsung; SM-G998U1; p3q; qcom; en_US; 559682050)"
    ),
    "X-IG-App-ID": "567067343352427",
    "X-IG-Device-ID": _DEVICE_ID,
    "X-IG-Android-ID": _ANDROID_ID,
    "Accept-Language": "en-US",
    "Accept-Encoding": "gzip, deflate",
}

# ── state ─────────────────────────────────────────────────────────────────────

_lock           = threading.Lock()
_last_call_time = 0.0
_cb_failures    = 0
_cb_open_until  = 0.0
_cache: dict[str, tuple[float, Any]] = {}
_uid_cache: dict[str, str] = {}   # username -> user_id (persisted in memory)


# ── rate limiter + circuit breaker ────────────────────────────────────────────

def _wait_for_slot() -> None:
    global _last_call_time
    elapsed = time.time() - _last_call_time
    gap = RATE_INTERVAL - elapsed
    if gap > 0:
        time.sleep(gap)
    _last_call_time = time.time()


def _circuit_open() -> bool:
    return time.time() < _cb_open_until


def _record_failure() -> None:
    global _cb_failures, _cb_open_until
    _cb_failures += 1
    if _cb_failures >= CB_FAILURE_THRESHOLD:
        _cb_open_until = time.time() + CB_RESET_AFTER
        logger.warning("Circuit opened after %d failures — pausing %ds", _cb_failures, CB_RESET_AFTER)


def _record_success() -> None:
    global _cb_failures, _cb_open_until
    _cb_failures = 0
    _cb_open_until = 0.0


# ── session helper ────────────────────────────────────────────────────────────

def _web_session() -> _req.Session:
    s = _req.Session()
    s.cookies.set("sessionid", _SESSIONID, domain=".instagram.com")
    s.headers.update(_WEB_HEADERS)
    return s


def _mobile_cookies() -> dict[str, str]:
    return {"sessionid": _SESSIONID}


# ── fetch helpers ─────────────────────────────────────────────────────────────

def _get_user_id(username: str) -> str:
    if username in _uid_cache:
        return _uid_cache[username]

    s = _web_session()
    r = s.get(
        f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}",
        timeout=15,
    )
    r.raise_for_status()
    uid = str(r.json()["data"]["user"]["id"])
    _uid_cache[username] = uid
    return uid


def _item_to_post(item: dict[str, Any], username: str) -> dict[str, Any]:
    cap_node = item.get("caption") or {}
    text = cap_node.get("text", "") if isinstance(cap_node, dict) else ""
    ts = item.get("taken_at", 0)
    posted_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None

    media_urls: list[str] = []
    # image
    if "image_versions2" in item:
        cands = item["image_versions2"].get("candidates", [])
        if cands:
            media_urls.append(cands[0]["url"])
    # video
    if item.get("video_versions"):
        media_urls.insert(0, item["video_versions"][0]["url"])
    # carousel
    if "carousel_media" in item:
        for cm in item["carousel_media"][:5]:
            cands = cm.get("image_versions2", {}).get("candidates", [])
            if cands:
                media_urls.append(cands[0]["url"])

    shortcode = item.get("code") or item.get("shortcode") or ""
    post_url = f"https://www.instagram.com/p/{shortcode}/" if shortcode else ""

    return {
        "platform": "instagram",
        "platform_post_id": str(item.get("id") or item.get("pk") or ""),
        "author_username": username,
        "author_name": None,
        "post_text": text.strip(),
        "post_url": post_url,
        "posted_at": posted_at,
        "likes": item.get("like_count"),
        "comments": item.get("comment_count"),
        "shares": None,
        "upvotes": None,
        "has_media": bool(media_urls),
        "media_urls": media_urls[:4],
        "raw": {
            "media_type": item.get("media_type"),
            "view_count": item.get("view_count"),
            "play_count": item.get("play_count"),
            "has_audio": item.get("has_audio"),
            "location": item.get("location", {}).get("name") if item.get("location") else None,
            "hashtags": [t.get("name") for t in (item.get("usertags") or {}).get("in", [])],
        },
    }


def _fetch_profile(username: str, limit: int) -> list[dict[str, Any]]:
    cache_key = f"profile:{username}:{limit}"
    now = time.time()

    if cache_key in _cache:
        expires_at, data = _cache[cache_key]
        if now < expires_at:
            logger.info("cache hit @%s", username)
            return data

    with _lock:
        if _circuit_open():
            raise RuntimeError(
                f"Circuit open until {time.strftime('%H:%M:%S', time.localtime(_cb_open_until))}"
            )

        backoff = 10.0
        for attempt in range(4):
            try:
                _wait_for_slot()
                user_id = _get_user_id(username)
                _wait_for_slot()
                r = _req.get(
                    f"https://i.instagram.com/api/v1/feed/user/{user_id}/",
                    params={"count": min(limit, 12), "rank_token": uuid.uuid4().hex},
                    headers=_MOBILE_HEADERS,
                    cookies=_mobile_cookies(),
                    timeout=20,
                )
                r.raise_for_status()
                items = r.json().get("items", [])[:limit]
                posts = [_item_to_post(it, username) for it in items]
                _record_success()
                _cache[cache_key] = (now + CACHE_TTL, posts)
                logger.info("fetched %d posts @%s", len(posts), username)
                return posts

            except (_req.HTTPError, _req.ConnectionError) as exc:
                status = getattr(exc.response, "status_code", 0) if hasattr(exc, "response") else 0
                logger.warning("HTTP error attempt %d @%s: %s (status %d) — backoff %.0fs",
                               attempt + 1, username, exc, status, backoff)
                _record_failure()
                if _circuit_open():
                    raise RuntimeError("Circuit opened mid-retry") from exc
                time.sleep(backoff)
                backoff = min(backoff * 2, 80)

            except Exception as exc:
                _record_failure()
                raise

    return []


# ── routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return jsonify({
        "status": "ok" if not _circuit_open() else "circuit_open",
        "cb_failures": _cb_failures,
        "session_loaded": bool(_SESSIONID),
        "uid_cache": list(_uid_cache.keys()),
    })


@app.get("/instagram/profile")
def profile_endpoint():
    username = request.args.get("username", "").strip().lstrip("@")
    if not username:
        return jsonify({"error": "username required"}), 400
    limit = min(int(request.args.get("limit", 20)), 50)

    try:
        posts = _fetch_profile(username, limit)
        return jsonify({"ok": True, "posts": posts, "count": len(posts)})
    except Exception as exc:
        logger.error("profile fetch failed @%s: %s", username, exc)
        return jsonify({"ok": False, "error": str(exc), "posts": []}), 503


# ── startup ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not _SESSIONID:
        logger.error("INSTA_SESSIONID env var not set — relay cannot authenticate")
        raise SystemExit(1)
    logger.info("Instagram relay starting on :%d", PORT)
    app.run(host="0.0.0.0", port=PORT, threaded=True)
