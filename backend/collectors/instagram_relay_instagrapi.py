"""
Instagram Relay Service (instagrapi engine) — durable-session variant.

Runs on a residential machine (this laptop). Hetzner calls this instead of
touching Instagram directly.

Why this exists (vs instagram_relay.py):
  The hand-rolled relay regenerated a NEW device fingerprint (uuid4) on every
  restart and managed only a bare `sessionid` cookie. Instagram binds sessions
  to the device that created them, so a shifting fingerprint + incomplete cookie
  jar got sessions invalidated fast ("session keeps dying"). instagrapi persists
  the FULL device state + cookies (dump_settings/load_settings) and reuses an
  identical fingerprint across restarts, so a sessionid seeded once via
  login_by_sessionid() lasts far longer and self-manages relogin/challenges.

Seeded WITHOUT a password: login_by_sessionid(<sessionid>) adopts an existing
session; instagrapi then owns the device/cookie persistence going forward.

Usage:
    pip install instagrapi flask
    set INSTA_SESSIONID=<sessionid cookie value>
    python instagram_relay_instagrapi.py        # listens on :8890

Endpoints (parity with instagram_relay.py):
    GET /health
    GET /instagram/profile?username=&limit=
    GET /instagram/profile_info?username=
    GET /instagram/post?shortcode=
    GET /instagram/comments?shortcode=&limit=
    GET /instagram/hashtag?tag=&limit=
    GET /instagram/stories?username=
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import timezone
from typing import Any

from flask import Flask, jsonify, request
from instagrapi import Client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s relay-ig %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("instagram_relay_instagrapi")

app = Flask(__name__)

# ── config ──────────────────────────────────────────────────────────────────
_SESSIONID     = os.getenv("INSTA_SESSIONID", "")
SETTINGS_FILE  = os.getenv("INSTA_SETTINGS_FILE",
                           os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "ig_relay_settings.json"))
PORT           = int(os.getenv("INSTAGRAM_RELAY_PORT", "8890"))
CACHE_TTL      = int(os.getenv("RELAY_CACHE_TTL", "600"))
# instagrapi inserts a random human-like delay in this range between private calls.
_DELAY_RANGE   = [int(os.getenv("RELAY_DELAY_MIN", "4")),
                  int(os.getenv("RELAY_DELAY_MAX", "9"))]

# ── state ───────────────────────────────────────────────────────────────────
_lock: threading.Lock = threading.Lock()
_client: Client | None = None
_cache: dict[str, tuple[float, Any]] = {}
_uid_cache: dict[str, str] = {}


# ── client bootstrap (persisted device + sessionid seed) ─────────────────────
def _get_client() -> Client:
    global _client
    if _client is not None:
        return _client
    cl = Client()
    cl.delay_range = _DELAY_RANGE
    # Restore the SAME device fingerprint + cookies used last time (durability).
    if os.path.exists(SETTINGS_FILE):
        try:
            cl.load_settings(SETTINGS_FILE)
            logger.info("loaded persisted device settings from %s", SETTINGS_FILE)
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not load settings (%s) — starting fresh device", exc)
    # Adopt the sessionid (no password). Refreshes auth onto the persisted device.
    if _SESSIONID:
        cl.login_by_sessionid(_SESSIONID)
    # Persist device + any refreshed cookies so the next restart is identical.
    try:
        cl.dump_settings(SETTINGS_FILE)
    except Exception as exc:  # noqa: BLE001
        logger.warning("dump_settings failed: %s", exc)
    _client = cl
    return cl


def _persist() -> None:
    if _client is not None:
        try:
            _client.dump_settings(SETTINGS_FILE)
        except Exception:  # noqa: BLE001
            pass


# ── mapping to the common post shape ─────────────────────────────────────────
def _media_to_post(m: Any, username: str) -> dict[str, Any]:
    urls: list[str] = []
    if getattr(m, "video_url", None):
        urls.append(str(m.video_url))
    elif getattr(m, "thumbnail_url", None):
        urls.append(str(m.thumbnail_url))
    for res in (getattr(m, "resources", None) or [])[:4]:
        u = getattr(res, "video_url", None) or getattr(res, "thumbnail_url", None)
        if u:
            urls.append(str(u))
    ts = getattr(m, "taken_at", None)
    code = getattr(m, "code", "") or ""
    return {
        "platform": "instagram",
        "platform_post_id": str(getattr(m, "pk", "") or ""),
        "author_username": username,
        "author_name": None,
        "post_text": (getattr(m, "caption_text", "") or "").strip(),
        "post_url": f"https://www.instagram.com/p/{code}/" if code else "",
        "posted_at": ts.astimezone(timezone.utc).isoformat() if ts else None,
        "likes": getattr(m, "like_count", None),
        "comments": getattr(m, "comment_count", None),
        "shares": None,
        "upvotes": None,
        "views": getattr(m, "view_count", None) or getattr(m, "play_count", None),
        "has_media": bool(urls),
        "media_urls": urls[:4],
        "raw": {
            "media_type": getattr(m, "media_type", None),
            "product_type": getattr(m, "product_type", None),
        },
    }


def _uid(username: str) -> str:
    if username in _uid_cache:
        return _uid_cache[username]
    uid = str(_get_client().user_id_from_username(username))
    _uid_cache[username] = uid
    return uid


# ── fetch helpers (all serialised under the lock) ────────────────────────────
def _fetch_profile(username: str, limit: int) -> list[dict[str, Any]]:
    key = f"profile:{username}:{limit}"
    now = time.time()
    if key in _cache and now < _cache[key][0]:
        logger.info("cache hit @%s", username)
        return _cache[key][1]
    with _lock:
        cl = _get_client()
        medias = cl.user_medias(int(_uid(username)), limit)
        posts = [_media_to_post(m, username) for m in medias]
        _persist()
        _cache[key] = (now + CACHE_TTL, posts)
        logger.info("fetched %d posts @%s (instagrapi)", len(posts), username)
        return posts


def _fetch_profile_info(username: str) -> dict[str, Any]:
    with _lock:
        u = _get_client().user_info_by_username(username)
        _persist()
        return {
            "platform": "instagram",
            "username": u.username,
            "full_name": u.full_name,
            "bio": (u.biography or "").strip(),
            "followers": u.follower_count,
            "following": u.following_count,
            "posts": u.media_count,
            "verified": u.is_verified,
            "private": u.is_private,
            "profile_pic": str(u.profile_pic_url_hd or u.profile_pic_url or ""),
            "external_url": str(u.external_url or "") or None,
            "category": u.category,
            "id": str(u.pk),
        }


def _fetch_post(shortcode: str) -> dict[str, Any] | None:
    with _lock:
        cl = _get_client()
        m = cl.media_info(cl.media_pk_from_code(shortcode))
        _persist()
        return _media_to_post(m, getattr(getattr(m, "user", None), "username", "") or "")


def _fetch_comments(shortcode: str, limit: int) -> list[dict[str, Any]]:
    with _lock:
        cl = _get_client()
        pk = cl.media_pk_from_code(shortcode)
        comments = cl.media_comments(pk, amount=limit)
        _persist()
        out = []
        for c in comments:
            ts = getattr(c, "created_at_utc", None) or getattr(c, "created_at", None)
            out.append({
                "platform": "instagram",
                "platform_post_id": str(getattr(c, "pk", "") or ""),
                "author_username": getattr(getattr(c, "user", None), "username", "") or "",
                "author_name": getattr(getattr(c, "user", None), "full_name", None),
                "post_text": (getattr(c, "text", "") or "").strip()[:4000],
                "post_url": f"https://www.instagram.com/p/{shortcode}/",
                "posted_at": ts.astimezone(timezone.utc).isoformat() if ts else None,
                "likes": getattr(c, "like_count", None),
                "comments": None, "shares": None, "upvotes": None,
                "has_media": False, "media_urls": [],
                "raw": {"parent_shortcode": shortcode},
            })
        return out


def _fetch_hashtag(tag: str, limit: int) -> list[dict[str, Any]]:
    with _lock:
        medias = _get_client().hashtag_medias_recent(tag.lstrip("#"), amount=limit)
        _persist()
        return [_media_to_post(m, getattr(getattr(m, "user", None), "username", "") or "")
                for m in medias]


def _fetch_stories(username: str) -> list[dict[str, Any]]:
    with _lock:
        cl = _get_client()
        stories = cl.user_stories(int(_uid(username)))
        _persist()
        out = []
        for s in stories:
            ts = getattr(s, "taken_at", None)
            url = str(getattr(s, "video_url", None) or getattr(s, "thumbnail_url", None) or "")
            out.append({
                "platform": "instagram",
                "platform_post_id": str(getattr(s, "pk", "") or ""),
                "author_username": username,
                "author_name": None,
                "post_text": "",
                "post_url": f"https://www.instagram.com/stories/{username}/{getattr(s,'pk','')}/",
                "posted_at": ts.astimezone(timezone.utc).isoformat() if ts else None,
                "likes": None, "comments": None, "shares": None, "upvotes": None,
                "has_media": bool(url),
                "media_urls": [url] if url else [],
                "raw": {"is_story": True, "media_type": getattr(s, "media_type", None)},
            })
        return out


# ── routes ───────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "engine": "instagrapi",
        "session_loaded": bool(_SESSIONID),
        "settings_persisted": os.path.exists(SETTINGS_FILE),
        "uid_cache": list(_uid_cache.keys()),
    })


def _envelope(fn, label: str, key: str = "posts"):
    try:
        data = fn()
        if key == "posts":
            return jsonify({"ok": True, "posts": data, "count": len(data)})
        return jsonify({"ok": True, "data": data})
    except Exception as exc:  # noqa: BLE001
        logger.error("%s failed: %s", label, exc)
        body = {"ok": False, "error": str(exc)}
        body["posts" if key == "posts" else "data"] = [] if key == "posts" else None
        return jsonify(body), 503


@app.get("/instagram/profile")
def profile_endpoint():
    u = request.args.get("username", "").strip().lstrip("@")
    if not u:
        return jsonify({"error": "username required"}), 400
    limit = min(int(request.args.get("limit", 20)), 50)
    return _envelope(lambda: _fetch_profile(u, limit), f"profile @{u}")


@app.get("/instagram/profile_info")
def profile_info_endpoint():
    u = request.args.get("username", "").strip().lstrip("@")
    if not u:
        return jsonify({"error": "username required"}), 400
    return _envelope(lambda: _fetch_profile_info(u), f"profile_info @{u}", key="data")


@app.get("/instagram/post")
def post_endpoint():
    sc = request.args.get("shortcode", "").strip()
    if not sc:
        return jsonify({"error": "shortcode required"}), 400
    return _envelope(lambda: _fetch_post(sc), f"post {sc}", key="data")


@app.get("/instagram/comments")
def comments_endpoint():
    sc = request.args.get("shortcode", "").strip()
    if not sc:
        return jsonify({"error": "shortcode required"}), 400
    limit = min(int(request.args.get("limit", 25)), 50)
    return _envelope(lambda: _fetch_comments(sc, limit), f"comments {sc}")


@app.get("/instagram/hashtag")
def hashtag_endpoint():
    tag = request.args.get("tag", "").strip().lstrip("#")
    if not tag:
        return jsonify({"error": "tag required"}), 400
    limit = min(int(request.args.get("limit", 25)), 50)
    return _envelope(lambda: _fetch_hashtag(tag, limit), f"hashtag #{tag}")


@app.get("/instagram/stories")
def stories_endpoint():
    u = request.args.get("username", "").strip().lstrip("@")
    if not u:
        return jsonify({"error": "username required"}), 400
    return _envelope(lambda: _fetch_stories(u), f"stories @{u}")


# ── startup ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not _SESSIONID and not os.path.exists(SETTINGS_FILE):
        logger.error("INSTA_SESSIONID env var not set and no persisted settings — cannot auth")
        raise SystemExit(1)
    logger.info("instagrapi relay starting on :%d (settings=%s)", PORT, SETTINGS_FILE)
    _get_client()  # eager auth so the first request is fast + failures surface at boot
    app.run(host="0.0.0.0", port=PORT, threaded=True)
