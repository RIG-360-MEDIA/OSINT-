"""Keyword-search collectors — one keyword in, real matched posts out.

Distinct from `pipeline_adapter.py` (which is HANDLE/CHANNEL oriented:
profile -> recent posts). This module is QUERY oriented: a free-text keyword ->
posts that match it, per platform, normalized to the `social_posts` dict shape.

Phase 1 scope: Reddit only. Other platforms register here as their keyword
methods are built (TikTok feed/search, YouTube search, Twitter twscrape, ...),
each as an `async (query, *, limit) -> KeywordSearchResult`. The verifier
iterates `REGISTRY`, so adding a platform is one line.

Every collector returns a `KeywordSearchResult` — never a raw list, never a bare
exception — so the caller always gets a normalized, self-describing outcome that
distinguishes "blocked / no session" from "genuinely zero matches". That
distinction is the whole point: a silent empty must never look like success.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

# Normalized post keys expected by the `social_posts` pipeline shape.
SOCIAL_POST_KEYS = (
    "platform", "platform_post_id", "author_username", "post_text",
    "post_url", "upvotes", "comment_count", "posted_at",
)


@dataclass(frozen=True)
class KeywordSearchResult:
    """Outcome of one keyword search on one platform. Immutable.

    ok=True with an empty `posts` means a genuine zero-match (query ran, nothing
    matched). ok=False means the method could not run (no session, HTTP block,
    exception) — `error` explains why. The verifier treats these very
    differently, so collectors MUST set `ok` honestly.
    """

    platform: str
    method: str
    query: str
    ok: bool
    posts: tuple[dict[str, Any], ...] = ()
    error: Optional[str] = None
    elapsed_s: float = 0.0
    note: Optional[str] = None          # honest limitation label, if any

    @property
    def count(self) -> int:
        return len(self.posts)


# ── Reddit ──────────────────────────────────────────────────────────────────

_REDDIT_DOMAIN = "reddit.com"


def _reddit_row_to_social_post(row: dict[str, Any], query: str) -> dict[str, Any]:
    """Map a RedditScraper post dict to the normalized social_posts shape.

    RedditScraper already emits most fields; the only rename is
    `comments` -> `comment_count`. `matched_keyword` is stamped for provenance
    (social_posts has no such column, so downstream persistence carries it in
    raw JSON — see handoff §2).
    """
    raw = row.get("raw") or {}
    external_url = raw.get("external_url") or ""
    domain = raw.get("domain") or ""
    # Text posts report domain "self.<sub>" and url == their own permalink (with a
    # www. that our permalink lacks). Only surface a genuine OUTBOUND link.
    if domain.startswith("self.") or external_url == (row.get("post_url") or ""):
        external_url = ""
    return {
        "platform": "reddit",
        "platform_post_id": row.get("platform_post_id") or "",
        "author_username": row.get("author_username") or "",
        "post_text": row.get("post_text") or "",
        "post_url": row.get("post_url") or "",
        "upvotes": int(row.get("upvotes") or 0),
        "comment_count": int(row.get("comments") or 0),
        "posted_at": row.get("posted_at") or "",
        "matched_keyword": query,
        "subreddit": raw.get("subreddit", ""),
        "has_media": bool(row.get("has_media")),
        # enriched OSINT fields
        "media_urls": list(row.get("media_urls") or []),
        "external_url": external_url,
        "domain": raw.get("domain") or "",
        "over_18": bool(raw.get("over_18")),
        "subreddit_subscribers": int(raw.get("subreddit_subscribers") or 0),
        "author_fullname": raw.get("author_fullname") or "",
        "upvote_ratio": raw.get("upvote_ratio"),
        "is_video": bool(raw.get("is_video")),
    }


def probe_reddit_session(session_token: Optional[str] = None) -> tuple[int, str]:
    """One authenticated request to report REAL session health, not a guess.

    Returns (http_status, detail). status -1 means the request itself failed
    (network/curl error). Lets the verifier say "session expired (403)" or
    "no cookie" instead of a misleading "0 results". Read-only, cheap.
    """
    token = session_token if session_token is not None else os.getenv("REDDIT_SESSION", "")
    if not token:
        return 0, "no REDDIT_SESSION cookie set"
    try:
        from curl_cffi.requests import Session

        with Session() as s:
            r = s.get(
                "https://www.reddit.com/r/india/new.json",
                params={"limit": 1, "raw_json": 1},
                cookies={"reddit_session": token},
                impersonate=os.getenv("REDDIT_IMPERSONATE", "chrome"),
                timeout=20,
            )
        if r.status_code == 200:
            return 200, "session OK"
        if r.status_code == 403:
            return 403, "403 — cookie expired/invalid or IP challenged"
        if r.status_code == 429:
            return 429, "429 — rate limited"
        return r.status_code, f"unexpected HTTP {r.status_code}"
    except Exception as exc:  # network/TLS failure is a real, reportable state
        return -1, f"{type(exc).__name__}: {exc}"


async def search_reddit(
    query: str,
    *,
    limit: int = 25,
    time_filter: str = "week",
    sort: str = "new",
    subreddit: Optional[str] = None,
    session_token: Optional[str] = None,
) -> KeywordSearchResult:
    """Free-text keyword search over Reddit (all, or one subreddit).

    Wraps the proven `RedditScraper.search` and normalizes to social_posts
    shape. Fails honestly (ok=False) when the session cookie is absent or the
    request is blocked — never returns a silent empty that looks like success.
    """
    method = "reddit_session_search" + (f"/r/{subreddit}" if subreddit else "/all")
    started = time.monotonic()

    token = session_token if session_token is not None else os.getenv("REDDIT_SESSION", "")
    if not token:
        return KeywordSearchResult(
            platform="reddit", method=method, query=query, ok=False,
            error="no REDDIT_SESSION cookie set (anon Reddit search is 403 from "
                  "all IPs — verified dev + Hetzner)",
            elapsed_s=time.monotonic() - started,
        )

    # Preflight: distinguish a dead/blocked session from a genuine zero-match.
    status, detail = probe_reddit_session(token)
    if status != 200:
        return KeywordSearchResult(
            platform="reddit", method=method, query=query, ok=False,
            error=f"session unhealthy: {detail}",
            elapsed_s=time.monotonic() - started,
        )

    try:
        from ..reddit_scraper import RedditScraper

        scraper = RedditScraper(session_token=token)
        raw_rows = await scraper.search(
            query, subreddit=subreddit, limit=limit, sort=sort,
            time_filter=time_filter,
        )
    except Exception as exc:
        return KeywordSearchResult(
            platform="reddit", method=method, query=query, ok=False,
            error=f"{type(exc).__name__}: {exc}",
            elapsed_s=time.monotonic() - started,
        )

    posts = tuple(_reddit_row_to_social_post(r, query) for r in raw_rows)
    return KeywordSearchResult(
        platform="reddit", method=method, query=query, ok=True,
        posts=posts, elapsed_s=time.monotonic() - started,
    )


# ── TikTok ──────────────────────────────────────────────────────────────────

def _iso(ts: Any) -> str:
    try:
        return datetime.fromtimestamp(float(ts or 0), tz=timezone.utc).isoformat()
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc).isoformat()


def _tiktok_vid_to_social_post(v: dict[str, Any], query: str) -> Optional[dict[str, Any]]:
    """Map a tikwm feed/search video to the normalized social_posts shape.

    TikTok has no upvote concept; likes (`digg_count`) map to `upvotes` so the
    unified shape holds. `views` (play_count) is kept as an extra.
    """
    vid = v.get("video_id") or v.get("aweme_id")
    if not vid:
        return None
    author = (v.get("author") or {}).get("unique_id") or ""
    return {
        "platform": "tiktok",
        "platform_post_id": str(vid),
        "author_username": author,
        "post_text": (v.get("title") or "").strip()[:2000],
        "post_url": f"https://www.tiktok.com/@{author}/video/{vid}",
        "upvotes": int(v.get("digg_count") or 0),
        "comment_count": int(v.get("comment_count") or 0),
        "posted_at": _iso(v.get("create_time")),
        "matched_keyword": query,
        "views": int(v.get("play_count") or 0),
        # enriched: a TikTok result IS a video — keep the playable media, not just the caption.
        "media_url": v.get("play") or "",          # no-watermark mp4 (CDN, signed/expiring)
        "thumbnail": v.get("cover") or "",
        "duration": int(v.get("duration") or 0),
        "region": v.get("region") or "",
        "shares": int(v.get("share_count") or 0),
    }


async def search_tiktok(
    query: str, *, limit: int = 25,
) -> KeywordSearchResult:
    """Free-text keyword search over TikTok via the free tikwm feed/search API.

    tikwm is a third-party mirror (no key, no cookie) — it breaks/rate-limits
    periodically, which is why it lives behind the same swap-able contract. Fails
    honestly (ok=False) on HTTP error or a non-zero tikwm code, so a transient
    outage is never mistaken for a genuine zero-match.
    """
    method = "tikwm_feed_search"
    started = time.monotonic()
    try:
        from curl_cffi.requests import AsyncSession

        async with AsyncSession() as s:
            r = await s.get(
                "https://www.tikwm.com/api/feed/search",
                params={"keywords": query, "count": min(limit, 30)},
                impersonate="chrome", timeout=25,
            )
        if r.status_code != 200:
            return KeywordSearchResult(
                platform="tiktok", method=method, query=query, ok=False,
                error=f"tikwm HTTP {r.status_code}",
                elapsed_s=time.monotonic() - started,
            )
        data = r.json()
        code = str(data.get("code"))
        if code != "0":
            return KeywordSearchResult(
                platform="tiktok", method=method, query=query, ok=False,
                error=f"tikwm code={code} msg={data.get('msg')!r} "
                      f"(rate-limit or upstream block)",
                elapsed_s=time.monotonic() - started,
            )
        videos = (data.get("data") or {}).get("videos") or []
    except Exception as exc:
        return KeywordSearchResult(
            platform="tiktok", method=method, query=query, ok=False,
            error=f"{type(exc).__name__}: {exc}",
            elapsed_s=time.monotonic() - started,
        )

    posts = tuple(
        p for p in (_tiktok_vid_to_social_post(v, query) for v in videos[:limit])
        if p is not None
    )
    return KeywordSearchResult(
        platform="tiktok", method=method, query=query, ok=True,
        posts=posts, elapsed_s=time.monotonic() - started,
    )


# ── registry ────────────────────────────────────────────────────────────────

# Each entry: platform -> async keyword-search callable. Add a line per platform
# as its keyword method ships. The verifier iterates this dict.
KeywordCollector = Callable[..., Awaitable[KeywordSearchResult]]

REGISTRY: dict[str, KeywordCollector] = {
    "reddit": search_reddit,
    "tiktok": search_tiktok,
}
