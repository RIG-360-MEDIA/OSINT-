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

import asyncio
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from typing import Any, Awaitable, Callable, Optional

from .osint_sources import all_telegram_channels

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


# ── YouTube ─────────────────────────────────────────────────────────────────

# Public YouTube WEB innertube key — a constant shipped in every youtube.com page,
# not a secret. Search needs no login and no PO token (only the player does).
_YT_INNERTUBE_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
_YT_CLIENT = {"clientName": "WEB", "clientVersion": "2.20240101.00.00",
              "hl": "en", "gl": "US"}

_YT_INT_RE = re.compile(r"[\d,]+")
_YT_REL_RE = re.compile(
    r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago")
_YT_UNIT_DAYS = {"second": 1 / 86400, "minute": 1 / 1440, "hour": 1 / 24,
                 "day": 1, "week": 7, "month": 30, "year": 365}


def _yt_int(text: Optional[str]) -> int:
    if not text:
        return 0
    m = _YT_INT_RE.search(text)
    return int(m.group(0).replace(",", "")) if m else 0


def _yt_relative_to_iso(text: Optional[str]) -> str:
    """Best-effort: YouTube search gives only relative time ('7 years ago').

    Approximate an ISO timestamp from it so downstream sorting/sanity works.
    The exact time is genuinely unavailable from search — the raw label is kept
    alongside in `published_text`, so this is an approximation, never a claim.
    """
    if not text:
        return ""
    m = _YT_REL_RE.search(text.lower())
    if not m:
        return ""
    from datetime import timedelta

    days = int(m.group(1)) * _YT_UNIT_DAYS[m.group(2)]
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _runs_text(node: dict[str, Any]) -> str:
    if not node:
        return ""
    if "simpleText" in node:
        return node["simpleText"]
    return "".join(r.get("text", "") for r in node.get("runs", []) or [])


def _yt_channel_id(vr: dict[str, Any]) -> str:
    """UC… channel id — bridges a keyword hit into the RSS discovery pipeline."""
    try:
        return (vr["ownerText"]["runs"][0]["navigationEndpoint"]
                ["browseEndpoint"]["browseId"]) or ""
    except (KeyError, IndexError, TypeError):
        return ""


def _yt_verified(vr: dict[str, Any]) -> bool:
    for badge in vr.get("ownerBadges") or []:
        if (badge.get("metadataBadgeRenderer") or {}).get("style") == \
                "BADGE_STYLE_TYPE_VERIFIED":
            return True
    return False


def _yt_renderer_to_social_post(vr: dict[str, Any], query: str) -> Optional[dict[str, Any]]:
    vid = vr.get("videoId")
    if not vid:
        return None
    title = _runs_text(vr.get("title", {}))
    # search snippet often carries the keyword when the title doesn't
    snippet = " ".join(
        _runs_text(s.get("snippetText", {}))
        for s in vr.get("detailedMetadataSnippets", []) or []
    )
    channel = _runs_text(vr.get("ownerText", {})) or _runs_text(vr.get("longBylineText", {}))
    published_text = _runs_text(vr.get("publishedTimeText", {}))
    thumbs = (vr.get("thumbnail", {}) or {}).get("thumbnails", []) or []
    return {
        "platform": "youtube",
        "platform_post_id": vid,
        "author_username": channel,
        "post_text": (title + ((" — " + snippet) if snippet else "")).strip()[:2000],
        "post_url": f"https://www.youtube.com/watch?v={vid}",
        # search exposes neither likes nor comment counts — 0 = not available here.
        "upvotes": 0,
        "comment_count": 0,
        "posted_at": _yt_relative_to_iso(published_text),
        "matched_keyword": query,
        "views": _yt_int(_runs_text(vr.get("viewCountText", {}))),
        "duration": _runs_text(vr.get("lengthText", {})),
        "thumbnail": thumbs[-1].get("url") if thumbs else "",
        "published_text": published_text,   # raw relative label (approximation source)
        # enriched: stable channel id (feeds RSS discovery) + credibility badge
        "channel_id": _yt_channel_id(vr),
        "verified": _yt_verified(vr),
    }


def _yt_walk_renderers(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull videoRenderer nodes from the innertube search response, defensively."""
    out: list[dict[str, Any]] = []
    try:
        sections = (
            data["contents"]["twoColumnSearchResultsRenderer"]["primaryContents"]
            ["sectionListRenderer"]["contents"]
        )
    except (KeyError, TypeError):
        return out
    for sec in sections:
        for item in (sec.get("itemSectionRenderer", {}) or {}).get("contents", []) or []:
            vr = item.get("videoRenderer")
            if vr:
                out.append(vr)
    return out


async def search_youtube(
    query: str, *, limit: int = 25,
) -> KeywordSearchResult:
    """Free-text keyword search over YouTube via the innertube search endpoint.

    No API key/quota (uses the public WEB client key), no login. RSS — the only
    datacenter-safe YouTube path — has no search, so this contacts Google
    directly; if the datacenter IP is challenged it fails honestly (ok=False)
    rather than looking like a genuine zero-match. Results are relevance-sorted,
    not recency-sorted, and carry no like/comment counts (search limitation).
    """
    method = "youtube_innertube_search"
    started = time.monotonic()
    try:
        from curl_cffi.requests import AsyncSession

        body = {"context": {"client": dict(_YT_CLIENT)}, "query": query}
        async with AsyncSession() as s:
            r = await s.post(
                f"https://www.youtube.com/youtubei/v1/search?key={_YT_INNERTUBE_KEY}",
                json=body, impersonate="chrome", timeout=25,
            )
        if r.status_code != 200:
            return KeywordSearchResult(
                platform="youtube", method=method, query=query, ok=False,
                error=f"innertube HTTP {r.status_code} "
                      f"(datacenter IP may be challenged — RSS-safe, search is not)",
                elapsed_s=time.monotonic() - started,
            )
        renderers = _yt_walk_renderers(r.json())
    except Exception as exc:
        return KeywordSearchResult(
            platform="youtube", method=method, query=query, ok=False,
            error=f"{type(exc).__name__}: {exc}",
            elapsed_s=time.monotonic() - started,
        )

    posts = tuple(
        p for p in (_yt_renderer_to_social_post(vr, query) for vr in renderers[:limit])
        if p is not None
    )
    return KeywordSearchResult(
        platform="youtube", method=method, query=query, ok=True,
        posts=posts, elapsed_s=time.monotonic() - started,
    )


# ── Twitter / X ─────────────────────────────────────────────────────────────

# Lazily-initialised twscrape wrapper (adds the cookie account to a pool DB once).
_twitter_scraper: Any = None


async def _get_twitter_scraper() -> Any:
    global _twitter_scraper
    if _twitter_scraper is None:
        from ..twitter_scraper import TwitterScraper

        scraper = TwitterScraper()
        await scraper.init()
        _twitter_scraper = scraper
    return _twitter_scraper


def _twitter_row_to_social_post(row: dict[str, Any], query: str) -> dict[str, Any]:
    """Map a TwitterScraper post to the normalized social_posts shape.

    Twitter has no upvotes; likes map to `upvotes`, replies to `comment_count`,
    retweets kept as `shares`. Views/lang/media are enriched extras.
    """
    raw = row.get("raw") or {}
    return {
        "platform": "twitter",
        "platform_post_id": row.get("platform_post_id") or "",
        "author_username": row.get("author_username") or "",
        "post_text": row.get("post_text") or "",
        "post_url": row.get("post_url") or "",
        "upvotes": int(row.get("likes") or 0),
        "comment_count": int(row.get("comments") or 0),
        "posted_at": row.get("posted_at") or "",
        "matched_keyword": query,
        # enriched
        "shares": int(row.get("shares") or 0),
        "views": int(raw.get("view_count") or 0),
        "lang": raw.get("lang") or "",
        "media_urls": list(row.get("media_urls") or []),
        "is_retweet": bool(raw.get("is_retweet")),
        "is_reply": bool(raw.get("is_reply")),
    }


async def search_twitter(
    query: str, *, limit: int = 25, product: str = "Latest",
) -> KeywordSearchResult:
    """Free-text keyword search over Twitter/X via twscrape (cookie-based).

    NOT the dead paid API — twscrape reuses a logged-in session cookie
    (TWITTER_AUTH_TOKEN + TWITTER_CT0). Fails honestly (ok=False) when the cookie
    is absent, so a missing session never looks like a genuine zero-match.
    """
    method = "twscrape_search"
    started = time.monotonic()
    if not (os.getenv("TWITTER_AUTH_TOKEN") and os.getenv("TWITTER_CT0")):
        return KeywordSearchResult(
            platform="twitter", method=method, query=query, ok=False,
            error="no TWITTER_AUTH_TOKEN/TWITTER_CT0 cookie set",
            elapsed_s=time.monotonic() - started,
        )
    try:
        scraper = await _get_twitter_scraper()
        rows = await scraper.search(query, limit=limit, product=product)
    except Exception as exc:
        return KeywordSearchResult(
            platform="twitter", method=method, query=query, ok=False,
            error=f"{type(exc).__name__}: {exc}",
            elapsed_s=time.monotonic() - started,
        )
    posts = tuple(_twitter_row_to_social_post(r, query) for r in rows)
    return KeywordSearchResult(
        platform="twitter", method=method, query=query, ok=True,
        posts=posts, elapsed_s=time.monotonic() - started,
    )


# ── Telegram (curated channel-set search — NOT global) ──────────────────────

_TG_STRIP = re.compile(r"<[^>]+>")
_TG_TEXT_RE = re.compile(
    r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.DOTALL)
_TG_TIME_RE = re.compile(r'<time[^>]*datetime="([^"]+)"')
_TG_VIEWS_RE = re.compile(r'tgme_widget_message_views"[^>]*>([^<]+)<')


def _tg_views_to_int(text: Optional[str]) -> int:
    """'1.2K' / '3.4M' / '512' -> int."""
    if not text:
        return 0
    t = text.strip().upper().replace(",", "")
    mult = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
    try:
        if t and t[-1] in mult:
            return int(float(t[:-1]) * mult[t[-1]])
        return int(float(t))
    except ValueError:
        return 0


def _parse_telegram(html: str, channel: str, query: str) -> list[dict[str, Any]]:
    """Parse matched messages from a t.me/s/{channel}?q= preview page.

    Splits per-message on data-post; local keyword re-check belts-and-braces
    Telegram's own filter.
    """
    tokens = [t for t in re.findall(r"[a-z0-9]+", query.lower())]
    posts: list[dict[str, Any]] = []
    for chunk in html.split('data-post="')[1:]:
        end = chunk.find('"')
        if end == -1:
            continue
        pid = chunk[:end]                       # e.g. "rybar/12345"
        m_text = _TG_TEXT_RE.search(chunk)
        if not m_text:
            continue
        text = unescape(_TG_STRIP.sub(" ", m_text.group(1))).strip()
        if not text:
            continue
        haystack = text.lower()
        if tokens and not any(t in haystack for t in tokens):
            continue
        m_time = _TG_TIME_RE.search(chunk)
        m_views = _TG_VIEWS_RE.search(chunk)
        posts.append({
            "platform": "telegram",
            "platform_post_id": pid,
            "author_username": channel,
            "post_text": text[:3000],
            "post_url": f"https://t.me/{pid}",
            "upvotes": 0,
            "comment_count": 0,
            "posted_at": (m_time.group(1) if m_time else ""),
            "matched_keyword": query,
            "views": _tg_views_to_int(m_views.group(1) if m_views else None),
            "channel": channel,
        })
    return posts


async def search_telegram(
    query: str, *, limit: int = 25,
) -> KeywordSearchResult:
    """Keyword search across a CURATED Telegram channel set (t.me/s/?q=).

    NOT global Telegram search (which is paid-only). Each channel's public
    preview is searched concurrently, no bot token. Always labelled with its
    honest scope so an empty result is a real 'nothing in these channels', not a
    silent failure.
    """
    method = "tme_channel_set_search"
    started = time.monotonic()
    channels = all_telegram_channels()
    note = f"within {len(channels)} curated channels (NOT global Telegram search)"

    sem = asyncio.Semaphore(8)

    async def _one(channel: str) -> list[dict[str, Any]]:
        async with sem:
            try:
                from curl_cffi.requests import AsyncSession

                async with AsyncSession() as s:
                    r = await s.get(
                        f"https://t.me/s/{channel}", params={"q": query},
                        impersonate="chrome", timeout=15,
                    )
                if r.status_code != 200:
                    return []
                return _parse_telegram(r.text, channel, query)
            except Exception:
                return []

    try:
        batches = await asyncio.gather(*[_one(c) for c in channels])
    except Exception as exc:
        return KeywordSearchResult(
            platform="telegram", method=method, query=query, ok=False,
            error=f"{type(exc).__name__}: {exc}", note=note,
            elapsed_s=time.monotonic() - started,
        )

    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for post in sorted(
        (p for batch in batches for p in batch),
        key=lambda x: x["posted_at"], reverse=True,
    ):
        if post["platform_post_id"] in seen:
            continue
        seen.add(post["platform_post_id"])
        merged.append(post)

    return KeywordSearchResult(
        platform="telegram", method=method, query=query, ok=True,
        posts=tuple(merged[:limit]), note=note,
        elapsed_s=time.monotonic() - started,
    )


# ── registry ────────────────────────────────────────────────────────────────

# Each entry: platform -> async keyword-search callable. Add a line per platform
# as its keyword method ships. The verifier iterates this dict.
KeywordCollector = Callable[..., Awaitable[KeywordSearchResult]]

REGISTRY: dict[str, KeywordCollector] = {
    "reddit": search_reddit,
    "tiktok": search_tiktok,
    "youtube": search_youtube,
    "twitter": search_twitter,
    "telegram": search_telegram,
}
