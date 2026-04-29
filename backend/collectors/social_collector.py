"""
Social media collectors — Reddit / Telegram.

Both return a common post dict shape that gets stored in `social_posts`.
All network errors are swallowed and logged — a single platform failure must
not poison a Celery task that covers multiple monitors.

Twitter / X was removed on 2026-04-29 — the API free tier returns HTTP
402 on user lookups, making collection non-functional. Restore from git
tag pre-twitter-removal if a paid tier is procured.
"""
from __future__ import annotations

import logging
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_REDDIT_UA = "RIGSurveillance/1.0 Intelligence Platform (contact: admin)"
_TELEGRAM_API = "https://api.telegram.org"

# SIG-8: Reddit 429 telemetry. Process-local; surfaces in
# /api/health/social if the platform exposes it. Escalates from WARNING
# to ERROR after _REDDIT_429_ESCALATE_AFTER consecutive throttles.
_reddit_429_streak: int = 0
_reddit_429_total: int = 0
_REDDIT_429_ESCALATE_AFTER: int = 3

def reddit_throttle_metrics() -> dict[str, int]:
    """Return current 429 counters (process-local)."""
    return {
        "streak": _reddit_429_streak,
        "total": _reddit_429_total,
        "escalate_after": _REDDIT_429_ESCALATE_AFTER,
    }


# ── Reddit ─────────────────────────────────────────────────────────────────

def _reddit_to_post(p: dict[str, Any]) -> dict[str, Any] | None:
    data = p.get("data") or {}
    post_id = data.get("id")
    if not post_id:
        return None

    title = data.get("title") or ""
    selftext = data.get("selftext") or ""
    combined = (title + " " + selftext).strip()[:3000]
    if not combined:
        return None

    return {
        "platform": "reddit",
        "platform_post_id": post_id,
        "author_username": data.get("author") or "",
        "post_text": combined,
        "post_url": "https://reddit.com" + (data.get("permalink") or ""),
        "upvotes": int(data.get("score") or 0),
        "comment_count": int(data.get("num_comments") or 0),
        "posted_at": datetime.fromtimestamp(
            float(data.get("created_utc") or 0),
            tz=timezone.utc,
        ).isoformat(),
    }


async def collect_reddit_posts(
    subreddit: str,
    limit: int = 25,
    category: str = "new",
) -> list[dict[str, Any]]:
    """Collect posts from a subreddit via Reddit's public JSON API."""
    url = (
        f"https://www.reddit.com/r/{subreddit}/{category}.json"
        f"?limit={limit}"
    )
    global _reddit_429_streak, _reddit_429_total
    try:
        async with httpx.AsyncClient(
            timeout=30, headers={"User-Agent": _REDDIT_UA}
        ) as client:
            r = await client.get(url)
            if r.status_code == 429:
                _reddit_429_streak += 1
                _reddit_429_total += 1
                msg = (
                    "Reddit rate-limited for r/%s (streak=%s, total=%s)"
                )
                if _reddit_429_streak >= _REDDIT_429_ESCALATE_AFTER:
                    logger.error(
                        msg, subreddit, _reddit_429_streak,
                        _reddit_429_total,
                    )
                else:
                    logger.warning(
                        msg, subreddit, _reddit_429_streak,
                        _reddit_429_total,
                    )
                return []
            if r.status_code != 200:
                logger.warning(
                    "Reddit error r/%s: %s", subreddit, r.status_code
                )
                return []
            _reddit_429_streak = 0  # success resets streak
            children = (r.json().get("data") or {}).get("children") or []
            return [p for p in (_reddit_to_post(c) for c in children) if p]
    except Exception as exc:
        logger.warning("Reddit collection failed r/%s: %s", subreddit, exc)
        return []


async def search_reddit_keyword(
    keyword: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search Reddit for a keyword via public JSON API."""
    q = urllib.parse.quote(keyword)
    url = f"https://www.reddit.com/search.json?q={q}&sort=new&limit={limit}"
    try:
        async with httpx.AsyncClient(
            timeout=30, headers={"User-Agent": _REDDIT_UA}
        ) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return []
            children = (r.json().get("data") or {}).get("children") or []
            return [p for p in (_reddit_to_post(c) for c in children) if p]
    except Exception as exc:
        logger.warning("Reddit search failed for %r: %s", keyword, exc)
        return []


# ── Twitter / X ────────────────────────────────────────────────────────────
# Removed 2026-04-29. Twitter API free tier returns HTTP 402 Payment
# Required for user lookups, making collection non-functional. Restore
# from git history (tag pre-twitter-removal) if a paid X tier is procured.


# ── Telegram ───────────────────────────────────────────────────────────────

def _telegram_message_to_post(
    msg: dict[str, Any], channel_username: str
) -> dict[str, Any] | None:
    message_id = msg.get("message_id")
    if not message_id:
        return None

    chat = msg.get("chat") or {}
    username = chat.get("username") or ""
    if channel_username.lower() not in username.lower():
        return None

    text = msg.get("text") or msg.get("caption") or ""
    if not text:
        return None

    forwarded_from = (msg.get("forward_from_chat") or {}).get("title") or ""
    document = msg.get("document") or {}
    has_doc = bool(document)

    return {
        "platform": "telegram",
        "platform_post_id": str(message_id),
        "author_username": username,
        "post_text": text[:3000],
        "post_url": f"https://t.me/{username}/{message_id}",
        "forward_count": int(msg.get("forward_count") or 0),
        "forwarded_from": forwarded_from,
        "has_document": has_doc,
        "document_url": document.get("file_id") if has_doc else None,
        "posted_at": datetime.fromtimestamp(
            float(msg.get("date") or 0),
            tz=timezone.utc,
        ).isoformat(),
    }


async def collect_telegram_channel(
    channel_username: str,
    bot_token: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Collect recent channel posts via Telegram Bot API polling."""
    if not bot_token:
        return []

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{_TELEGRAM_API}/bot{bot_token}/getUpdates",
                params={
                    "limit": limit,
                    "allowed_updates": '["channel_post"]',
                },
            )
            if r.status_code != 200:
                logger.warning("Telegram API error: %s", r.status_code)
                return []

            updates = r.json().get("result") or []
            posts: list[dict[str, Any]] = []
            for update in updates:
                msg = update.get("channel_post")
                if not msg:
                    continue
                post = _telegram_message_to_post(msg, channel_username)
                if post:
                    posts.append(post)
            return posts
    except Exception as exc:
        logger.warning(
            "Telegram collection failed for %s: %s", channel_username, exc
        )
        return []


# ── Sentiment analysis ─────────────────────────────────────────────────────

def compute_sentiment(text: str, language: str = "en") -> float:
    """
    Return sentiment in [-1.0, +1.0].

    VADER for English (fast, local). TextBlob fallback for other languages.
    Returns 0.0 on any failure.
    """
    if not text:
        return 0.0
    try:
        if language == "en":
            from vaderSentiment.vaderSentiment import (
                SentimentIntensityAnalyzer,
            )
            return SentimentIntensityAnalyzer().polarity_scores(text)[
                "compound"
            ]
        from textblob import TextBlob
        return float(TextBlob(text).sentiment.polarity)
    except Exception as exc:
        logger.debug("sentiment failed: %s", exc)
        return 0.0


# ── Entity matching ────────────────────────────────────────────────────────

import re as _re_match  # local alias to avoid clobbering top-level if any


def _word_boundary(name: str) -> _re_match.Pattern[str]:
    """Build a case-insensitive whole-word matcher for a name.

    \\b alone fails for non-ASCII (Telugu/Hindi/etc.). We pad with
    look-around for non-letter chars in either Unicode script. This stops
    "RT" matching inside "PARTY" while still matching Telugu names
    surrounded by punctuation.
    """
    return _re_match.compile(
        r"(?<![\wऀ-ॿఀ-౿])"
        + _re_match.escape(name)
        + r"(?![\wऀ-ॿఀ-౿])",
        _re_match.IGNORECASE,
    )


# Module-level cache — recompiling 11k regexes per post is wasteful.
_PATTERN_CACHE: dict[str, _re_match.Pattern[str]] = {}


def _pattern_for(name: str) -> _re_match.Pattern[str]:
    pat = _PATTERN_CACHE.get(name)
    if pat is None:
        pat = _word_boundary(name)
        _PATTERN_CACHE[name] = pat
    return pat


def find_matched_entities(
    text: str,
    user_entities: list[str],
    *,
    text_translated: str | None = None,
    aliases: dict[str, list[str]] | None = None,
) -> list[str]:
    """Case-insensitive whole-word match — entity canonical name in post.

    Args:
        text: Post body in its original language.
        user_entities: Canonical names to look for.
        text_translated: Optional English translation of `text`. When given,
            both source and translation are scanned — lets English entity
            names match Telugu/Hindi/etc. posts via the English mirror.
        aliases: Optional `{canonical_name: [alias1, alias2, ...]}` map.
            A hit on any alias counts as a hit on the canonical name.

    Returns canonical names (deduplicated, original casing preserved).
    """
    if not user_entities:
        return []
    haystack = " ".join(filter(None, [text or "", text_translated or ""]))
    if not haystack.strip():
        return []
    aliases = aliases or {}
    out: list[str] = []
    seen: set[str] = set()
    for name in user_entities:
        if not name or name in seen:
            continue
        candidates = [name, *(aliases.get(name) or [])]
        for cand in candidates:
            if not cand:
                continue
            if _pattern_for(cand).search(haystack):
                out.append(name)
                seen.add(name)
                break
    return out
