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
from urllib.parse import unquote

from .osint_sources import WECHAT_TERM_MAP, all_telegram_channels

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
# link + media extraction
_TG_HREF_RE = re.compile(r'href="([^"]+)"')
_TG_URL_RE = re.compile(r'https?://[^\s"<>]+')
_TG_PHOTO_RE = re.compile(r"tgme_widget_message_photo_wrap[^>]*?url\('([^']+)'\)")
_TG_VIDEOTHUMB_RE = re.compile(r"tgme_widget_message_video_thumb[^>]*?url\('([^']+)'\)")
_TG_VIDEOSRC_RE = re.compile(r'<video[^>]+src="([^"]+)"')


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    return [x for x in items if not (x in seen or seen.add(x))]


# Donation / promo domains channels stamp on every post — boilerplate, not content.
_TG_PROMO_DOMAINS = (
    "ko-fi.com", "patreon.com", "buymeacoffee.com", "paypal.me", "boosty.to",
    "donate", "streamlabs.com",
)


def _tg_extract_links(text_html: str, clean_text: str) -> list[str]:
    """Outbound content links from a message: absolute http(s) <a href> +
    plaintext URLs, minus telegram-internal links, relative hrefs (#hashtag,
    ?q=…), and donation/promo boilerplate."""
    urls = [unescape(u) for u in _TG_HREF_RE.findall(text_html)]
    urls += _TG_URL_RE.findall(clean_text)
    out: list[str] = []
    for u in urls:
        if not u.startswith(("http://", "https://")):   # drop relative (#, ?q=, /)
            continue
        if u.startswith(("https://t.me/", "http://t.me/")):
            continue
        low = u.lower()
        if any(d in low for d in _TG_PROMO_DOMAINS):
            continue
        out.append(u)
    return _dedupe(out)


def _tg_extract_media(chunk: str) -> list[str]:
    """Photo / video-thumb / video-src URLs from a message block."""
    media = (_TG_PHOTO_RE.findall(chunk)
             + _TG_VIDEOTHUMB_RE.findall(chunk)
             + _TG_VIDEOSRC_RE.findall(chunk))
    return _dedupe([unescape(m) for m in media])


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
        text_html = m_text.group(1)
        text = unescape(_TG_STRIP.sub(" ", text_html)).strip()
        if not text:
            continue
        haystack = text.lower()
        if tokens and not any(t in haystack for t in tokens):
            continue
        m_time = _TG_TIME_RE.search(chunk)
        m_views = _TG_VIEWS_RE.search(chunk)
        links = _tg_extract_links(text_html, text)
        media = _tg_extract_media(chunk)
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
            # enriched: outbound links + media pulled out of the message
            "external_urls": links,
            "external_url": links[0] if links else "",
            "media_urls": media,
            "has_media": bool(media),
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


# ── Instagram (global keyword search via search-engine index) ───────────────
# IG has no free global caption search and hashtag needs a login. But search
# engines INDEX instagram.com captions, so `site:instagram.com "keyword"` on
# DuckDuckGo returns global keyword-matched posts — no login, no account set.
# IG's own og:description ("N likes, M comments - user on DATE: caption") is
# indexed too, so the snippet often yields author/engagement/date for free.

_DDG_BLOCK_RE = re.compile(
    r'result__a[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?result__snippet[^>]*>(.*?)</a>',
    re.DOTALL)
_IG_SHORTCODE_RE = re.compile(r"instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)")
_UDDG_RE = re.compile(r"uddg=([^&]+)")
_IG_META_RE = re.compile(
    r"^\s*([\d.,KMB]+)\s+likes?,\s*([\d.,KMB]+)\s+comments?\s*-\s*([\w.]+)\s+on\s+"
    r"([A-Za-z]+ \d+, \d{4}):\s*(.*)$", re.DOTALL)


def _ig_parse_date(text: str) -> str:
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return ""


def _ddg_ig_to_post(url: str, snippet: str, query: str) -> Optional[dict[str, Any]]:
    """Map one DDG instagram.com result to the social_posts shape.

    Parses IG's indexed og:description for author/likes/comments/date when
    present; otherwise the snippet IS the caption and engagement is unknown (0).
    """
    sc = _IG_SHORTCODE_RE.search(url)
    if not sc:
        return None
    caption, author, likes, comments, posted = snippet, "", 0, 0, ""
    m = _IG_META_RE.match(snippet)
    if m:
        likes = _tg_views_to_int(m.group(1))       # handles 64K / 1.2M
        comments = _tg_views_to_int(m.group(2))
        author = m.group(3)
        posted = _ig_parse_date(m.group(4))
        caption = m.group(5).strip().strip('"').strip()
    return {
        "platform": "instagram",
        "platform_post_id": sc.group(1),
        "author_username": author,
        "post_text": caption[:2000],
        "post_url": f"https://www.instagram.com/p/{sc.group(1)}/",
        "upvotes": likes,
        "comment_count": comments,
        "posted_at": posted,
        "matched_keyword": query,
    }


_IG_OG_RE = re.compile(r'og:description"\s+content="([^"]+)"')
_IG_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_SEARXNG_URL = os.getenv("SEARXNG_URL", "http://rig-searxng:8080")


async def _ig_discover(query: str, session: Any, want: int) -> list[str]:
    """Return IG shortcodes for a keyword. SearXNG (self-hosted, no direct
    rate-limit) first; DuckDuckGo direct as fallback (e.g. on dev, no SearXNG)."""
    codes: list[str] = []
    # 1) SearXNG meta-search — try exact phrase AND broad (each surfaces
    #    different posts; broad also catches /tv/ and reel URLs)
    for phrase in (f'site:instagram.com "{query}"', f"site:instagram.com {query}"):
        try:
            r = await session.get(
                _SEARXNG_URL + "/search",
                params={"q": phrase, "format": "json"}, timeout=15,
            )
            if r.status_code == 200 and r.text.lstrip().startswith("{"):
                for item in r.json().get("results", []):
                    m = _IG_SHORTCODE_RE.search(item.get("url") or "")
                    if m:
                        codes.append(m.group(1))
        except Exception:
            continue
    if len(codes) < want:   # 2) DuckDuckGo direct fallback / top-up
        try:
            q = f'site:instagram.com "{query}"'.replace(" ", "+")
            r = await session.get(
                "https://html.duckduckgo.com/html/?q=" + q,
                headers=_IG_UA, impersonate="chrome", timeout=20,
            )
            if r.status_code == 200:
                for href, _t, _s in _DDG_BLOCK_RE.findall(r.text):
                    mu = _UDDG_RE.search(href)
                    m = _IG_SHORTCODE_RE.search(unquote(mu.group(1)) if mu else href)
                    if m:
                        codes.append(m.group(1))
        except Exception:
            pass
    seen: set[str] = set()
    return [c for c in codes if not (c in seen or seen.add(c))][:want * 2]


async def _ig_fetch_og(shortcode: str, session: Any) -> Optional[str]:
    """Fetch a post's og:description ('N likes, M comments - user on DATE:
    caption') — works cookie-free from the datacenter."""
    try:
        r = await session.get(
            f"https://www.instagram.com/p/{shortcode}/",
            headers=_IG_UA, impersonate="chrome", timeout=15,
        )
        if r.status_code != 200:
            return None
        m = _IG_OG_RE.search(r.text)
        return unescape(m.group(1)) if m else None
    except Exception:
        return None


# Persist-from-use (in-process): keyword -> relevant author handles, so repeat
# searches refresh the same accounts (fresher + faster). Grows during a session.
_ig_author_cache: dict[str, set[str]] = {}
_IG_MAX_ACCOUNTS = 12   # bound the real-time fan-out (web_profile_info ~200/hr/IP)


async def search_instagram(
    query: str, *, limit: int = 25,
) -> KeywordSearchResult:
    """Global + real-time keyword search over Instagram — free, NO login, NO
    ban risk, NO manually-preset account set.

    Hybrid of two cookie-free techniques, both proven from the datacenter box:
      1) DISCOVER (global): search-index (SearXNG/DDG) `site:instagram.com "kw"`
         → post URLs; og:description → caption + the AUTHOR handle. This finds
         who-posts-about-this anywhere on IG (no preset accounts — the keyword
         builds the account list).
      2) REFRESH (real-time): web_profile_info on those auto-discovered accounts
         → their NEWEST posts → keyword-filter. Fresh, cookie-free, no account.
      Merge (dedupe by shortcode; real-time overrides stale index copy).

    Honest gap: catches real-time posts from any account the index has EVER seen
    on-topic (news orgs, official/known handles) — not a brand-new, never-indexed
    account's post the instant it's made (that needs the login-walled firehose).
    """
    method = "searxng_discover+web_profile_realtime"
    started = time.monotonic()
    note = ("global keyword search: search-index discovery + web_profile_info "
            "real-time refresh of matched accounts (free, login-free); brand-new "
            "un-indexed accounts not caught")
    phrase = query.lower().strip()
    # Drop 1-char/ambiguous tokens; require the FULL phrase OR all tokens so a
    # loose token can't pull noise (e.g. "pla" matching #pla=plastic model kits).
    toks = [t for t in re.findall(r"[a-z0-9]+", phrase) if len(t) >= 2]
    ckey = phrase

    def _match(post: dict[str, Any]) -> bool:
        hay = ((post.get("post_text") or "") + " " +
               (post.get("author_username") or "")).lower()
        if phrase and phrase in hay:
            return True                       # exact phrase = strongest
        return (not toks) or all(t in hay for t in toks)

    merged: dict[str, dict[str, Any]] = {}
    index_posts: list[dict[str, Any]] = []
    try:
        from curl_cffi.requests import AsyncSession
        from .pipeline_adapter import collect_instagram_posts

        # ── Stage 1: DISCOVER (global search-index) + caption/author enrich ──
        async with AsyncSession() as s:
            codes = await _ig_discover(query, s, limit)
            sem = asyncio.Semaphore(6)

            async def _enrich(sc: str) -> Optional[dict[str, Any]]:
                async with sem:
                    og = await _ig_fetch_og(sc, s)
                    return (_ddg_ig_to_post(
                        f"https://www.instagram.com/p/{sc}/", og, query)
                        if og else None)

            index_posts = [p for p in await asyncio.gather(
                *[_enrich(c) for c in codes]) if p]
        for p in index_posts:
            if _match(p):
                merged[p["platform_post_id"]] = {**p, "source": "index",
                                                  "is_realtime": False}

        # relevant accounts = discovered + remembered (persist-from-use)
        authors = {p["author_username"] for p in index_posts if p.get("author_username")}
        authors |= _ig_author_cache.get(ckey, set())
        authors = sorted(a for a in authors if a)[:_IG_MAX_ACCOUNTS]

        # ── Stage 2: REAL-TIME refresh of those accounts (web_profile_info) ──
        batches = await asyncio.gather(
            *[asyncio.to_thread(collect_instagram_posts, a, limit=8) for a in authors],
            return_exceptions=True,
        )
        for batch in batches:
            if isinstance(batch, Exception) or not batch:
                continue
            for p in batch:
                if _match(p):
                    merged[p["platform_post_id"]] = {
                        **p, "matched_keyword": query,
                        "source": "realtime", "is_realtime": True}
    except Exception as exc:
        return KeywordSearchResult(
            platform="instagram", method=method, query=query, ok=False,
            error=f"{type(exc).__name__}: {exc}", note=note,
            elapsed_s=time.monotonic() - started,
        )

    if authors:   # remember relevant accounts for next time
        _ig_author_cache.setdefault(ckey, set()).update(authors)

    ordered = sorted(merged.values(), key=lambda x: x.get("posted_at") or "",
                     reverse=True)
    return KeywordSearchResult(
        platform="instagram", method=method, query=query, ok=True,
        posts=tuple(ordered[:limit]), note=note,
        elapsed_s=time.monotonic() - started,
    )


# ── WeChat (public Official-Account articles) ───────────────────────────────
# China's public press/state-media space — highest-differentiation source.
# DISCOVER via search-index (site:mp.weixin.qq.com — no China IP needed) +
# FETCH each article's full content via curl_cffi (proven from datacenter).
# Chinese-language. Moments / private accounts / DMs are OFF-LIMITS.

_WX_TITLE_RE = re.compile(r'property="og:title" content="([^"]*)"')
_WX_ACCT_RE = re.compile(r'id="js_name">\s*([^<]+)')
_WX_CT_RE = re.compile(r'var ct = "(\d+)"')
_WX_CONTENT_RE = re.compile(r'id="js_content"[^>]*>(.*)', re.DOTALL)


def _wx_post_id(url: str) -> str:
    m = re.search(r"/s/([A-Za-z0-9_-]+)", url)
    if m:
        return "wx_" + m.group(1)
    mid = re.search(r"mid=(\d+)", url)
    idx = re.search(r"idx=(\d+)", url)
    if mid:
        return f"wx_{mid.group(1)}_{idx.group(1) if idx else '1'}"
    return "wx_" + url[-24:]


def _wechat_parse(url: str, html: str, query: str) -> Optional[dict[str, Any]]:
    tm = _WX_TITLE_RE.search(html)
    title = unescape(tm.group(1)).strip() if tm else ""
    am = _WX_ACCT_RE.search(html)
    account = unescape(am.group(1)).strip() if am else ""
    cm = _WX_CT_RE.search(html)
    posted = _iso(int(cm.group(1))) if cm else ""
    content = ""
    com = _WX_CONTENT_RE.search(html)
    if com:
        content = unescape(_TG_STRIP.sub(" ", com.group(1)[:80000]))
        content = re.sub(r"\s+", " ", content).strip()[:6000]
    if not title and not content:
        return None
    return {
        "platform": "wechat",
        "platform_post_id": _wx_post_id(url),
        "author_username": account,
        "post_text": (title + ((" — " + content[:400]) if content else ""))[:2000],
        "post_url": url,
        "upvotes": 0,
        "comment_count": 0,
        "posted_at": posted,
        "matched_keyword": query,
        "account": account,          # the Official Account
        "title": title,
        "content": content,          # full article body (the differentiator)
    }


_WX_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
_GTX_URL = "https://translate.googleapis.com/translate_a/single"


def _has_cjk(text: str) -> bool:
    return any("一" <= c <= "鿿" for c in text)


async def _translate_to_zh(text: str, session: Any) -> Optional[str]:
    """English -> Chinese. Curated OSINT dict first (exact), then Google's free
    keyless gtx endpoint (works from datacenter). None if both miss."""
    hit = WECHAT_TERM_MAP.get(text.strip().lower())
    if hit:
        return hit
    try:
        r = await session.get(
            _GTX_URL,
            params={"client": "gtx", "sl": "en", "tl": "zh-CN", "dt": "t", "q": text},
            impersonate="chrome", timeout=12,
        )
        if r.status_code == 200:
            zh = "".join(seg[0] for seg in r.json()[0] if seg and seg[0])
            return zh.strip() or None
    except Exception:
        pass
    return None


async def _wechat_query_terms(query: str, session: Any) -> list[str]:
    """Query variants to search on WeChat: the original + its Chinese term
    (WeChat is Chinese-language, so English alone under-returns). Searching both
    maximizes recall (some articles use transliterated/English terms)."""
    terms = [query]
    if not _has_cjk(query):
        zh = await _translate_to_zh(query, session)
        if zh and zh != query:
            terms.append(zh)
    seen: set[str] = set()
    return [t for t in terms if t and not (t in seen or seen.add(t))]


async def _wechat_discover_sogou(query: str, session: Any, want: int) -> list[str]:
    """Discover mp.weixin.qq.com articles via Sogou Weixin — Tencent's OFFICIAL
    WeChat search index (reliable, indexes WeChat properly, unlike western
    engines). Works from the datacenter with cookie-priming + Chrome TLS.

    Flow: prime cookies → article search (type=2) → each result links via a
    /link?url= redirect whose real URL is assembled in JS `url += '...'` pieces.
    """
    try:
        await session.get("https://weixin.sogou.com/", headers=_WX_UA,
                          impersonate="chrome", timeout=15)
        r = await session.get(
            "https://weixin.sogou.com/weixin",
            params={"type": "2", "query": query, "ie": "utf8", "s_from": "input"},
            headers={**_WX_UA, "Referer": "https://weixin.sogou.com/"},
            impersonate="chrome", timeout=20,
        )
        if r.status_code != 200:
            return []
        hrefs = re.findall(r'<h3>\s*<a[^>]*href="(/link\?url=[^"]+)"', r.text)
    except Exception:
        return []

    sem = asyncio.Semaphore(6)

    async def _resolve(href: str) -> Optional[str]:
        async with sem:
            try:
                lr = await session.get(
                    "https://weixin.sogou.com" + href.replace("&amp;", "&"),
                    headers={**_WX_UA, "Referer": "https://weixin.sogou.com/"},
                    impersonate="chrome", timeout=15,
                )
                real = "".join(re.findall(r"url \+= '([^']*)'", lr.text))
                return real if "mp.weixin.qq.com" in real else None
            except Exception:
                return None

    resolved = await asyncio.gather(*[_resolve(h) for h in hrefs[:want]])
    seen: set[str] = set()
    return [u for u in resolved if u and not (u in seen or seen.add(u))]


async def _wechat_discover(query: str, session: Any, want: int) -> list[str]:
    """mp.weixin.qq.com article URLs. Sogou Weixin (reliable) first, then
    search-index (SearXNG/DDG) as fallback."""
    urls = await _wechat_discover_sogou(query, session, want)
    if urls:
        return urls[:want]
    for _ in range(2):
        try:
            r = await session.get(
                _SEARXNG_URL + "/search",
                params={"q": f"site:mp.weixin.qq.com {query}", "format": "json"},
                timeout=15,
            )
            if r.status_code == 200 and r.text.lstrip().startswith("{"):
                for x in r.json().get("results", []):
                    u = x.get("url") or ""
                    if "mp.weixin.qq.com/s" in u:
                        urls.append(u)
                if urls:
                    break
        except Exception:
            continue
    if not urls:
        try:
            q = f"site:mp.weixin.qq.com {query}".replace(" ", "+")
            r = await session.get("https://html.duckduckgo.com/html/?q=" + q,
                                  headers=_IG_UA, impersonate="chrome", timeout=20)
            if r.status_code == 200:
                for m in re.findall(r'uddg=([^&"]+)', r.text):
                    u = unquote(m)
                    if "mp.weixin.qq.com/s" in u:
                        urls.append(u)
        except Exception:
            pass
    seen: set[str] = set()
    return [u for u in urls if not (u in seen or seen.add(u))][:want]


async def search_wechat(
    query: str, *, limit: int = 25,
) -> KeywordSearchResult:
    """Keyword search over PUBLIC WeChat Official-Account articles.

    DISCOVER via search-index (`site:mp.weixin.qq.com`, no China IP) + FETCH each
    article's full content (curl_cffi, works from datacenter). Chinese-language.
    Moments / private accounts / DMs are OFF-LIMITS.
    """
    method = "sogou_weixin+zh_map+content_fetch"
    started = time.monotonic()
    note = ("public WeChat Official-Account articles via Sogou Weixin (Tencent's "
            "official WeChat search; search-index fallback) + EN->ZH term mapping "
            "+ full-content fetch; Chinese-language; Moments/private OFF-LIMITS")

    try:
        from curl_cffi.requests import AsyncSession

        async with AsyncSession() as s:
            # EN -> [en, zh] so English keywords hit this Chinese-language platform
            terms = await _wechat_query_terms(query, s)
            match_toks = [t.lower() for t in terms]

            url_terms: dict[str, str] = {}   # article url -> the term that found it
            for term in terms:
                for u in await _wechat_discover(term, s, limit):
                    url_terms.setdefault(u, term)

            sem = asyncio.Semaphore(5)

            async def _one(item: tuple[str, str]) -> Optional[dict[str, Any]]:
                u, term = item
                async with sem:
                    try:
                        r = await s.get(u, impersonate="chrome", timeout=20)
                        return _wechat_parse(u, r.text, term) if r.status_code == 200 else None
                    except Exception:
                        return None

            results = await asyncio.gather(*[_one(it) for it in url_terms.items()])
    except Exception as exc:
        return KeywordSearchResult(
            platform="wechat", method=method, query=query, ok=False,
            error=f"{type(exc).__name__}: {exc}", note=note,
            elapsed_s=time.monotonic() - started,
        )

    posts: dict[str, dict[str, Any]] = {}
    for p in results:
        if not p:
            continue
        hay = (p["title"] + " " + p["content"] + " " + p["account"]).lower()
        if match_toks and not any(t in hay for t in match_toks):
            continue
        posts.setdefault(p["platform_post_id"], p)

    ordered = sorted(posts.values(), key=lambda x: x.get("posted_at") or "", reverse=True)
    return KeywordSearchResult(
        platform="wechat", method=method, query=query, ok=True,
        posts=tuple(ordered[:limit]), note=note,
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
    "instagram": search_instagram,
    "wechat": search_wechat,
}
