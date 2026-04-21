"""
Social media collectors — Reddit / Twitter / Telegram.

All three return a common post dict shape that gets stored in `social_posts`.
All network errors are swallowed and logged — a single platform failure must
not poison a Celery task that covers multiple monitors.
"""
from __future__ import annotations

import logging
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_REDDIT_UA = "RIGSurveillance/1.0 Intelligence Platform (contact: admin)"
_TWITTER_API = "https://api.twitter.com"
_TELEGRAM_API = "https://api.telegram.org"


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
    try:
        async with httpx.AsyncClient(
            timeout=30, headers={"User-Agent": _REDDIT_UA}
        ) as client:
            r = await client.get(url)
            if r.status_code == 429:
                logger.warning("Reddit rate-limited for r/%s", subreddit)
                return []
            if r.status_code != 200:
                logger.warning(
                    "Reddit error r/%s: %s", subreddit, r.status_code
                )
                return []
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

def _twitter_tweet_to_post(
    t: dict[str, Any], username: str
) -> dict[str, Any] | None:
    tid = t.get("id")
    text = t.get("text") or ""
    if not tid or not text:
        return None
    metrics = t.get("public_metrics") or {}
    return {
        "platform": "twitter",
        "platform_post_id": str(tid),
        "author_username": username,
        "post_text": text[:3000],
        "post_url": (
            f"https://twitter.com/{username}/status/{tid}"
            if username
            else f"https://twitter.com/i/web/status/{tid}"
        ),
        "upvotes": int(metrics.get("like_count") or 0),
        "comment_count": int(metrics.get("reply_count") or 0),
        "share_count": int(metrics.get("retweet_count") or 0),
        "post_language": t.get("lang") or "en",
        "posted_at": t.get("created_at"),
    }


async def collect_twitter_user_tweets(
    username: str,
    bearer_token: str,
    max_results: int = 10,
    since_id: str | None = None,
) -> list[dict[str, Any]]:
    """Collect recent tweets from a user via Twitter API v2 (Bearer Token)."""
    if not bearer_token:
        return []

    try:
        async with httpx.AsyncClient(
            timeout=30,
            headers={"Authorization": f"Bearer {bearer_token}"},
        ) as client:
            user_r = await client.get(
                f"{_TWITTER_API}/2/users/by/username/{username}",
                params={"user.fields": "public_metrics"},
            )
            if user_r.status_code != 200:
                logger.warning(
                    "Twitter user lookup failed @%s: %s",
                    username,
                    user_r.status_code,
                )
                return []
            user_id = ((user_r.json().get("data") or {}).get("id"))
            if not user_id:
                return []

            params: dict[str, Any] = {
                "max_results": min(max(max_results, 5), 100),
                "tweet.fields": "created_at,public_metrics,lang",
                "expansions": "author_id",
            }
            if since_id:
                params["since_id"] = since_id

            tweets_r = await client.get(
                f"{_TWITTER_API}/2/users/{user_id}/tweets",
                params=params,
            )
            if tweets_r.status_code != 200:
                logger.warning(
                    "Twitter tweets failed @%s: %s",
                    username,
                    tweets_r.status_code,
                )
                return []

            tweets = tweets_r.json().get("data") or []
            return [
                p
                for p in (_twitter_tweet_to_post(t, username) for t in tweets)
                if p
            ]
    except Exception as exc:
        logger.warning("Twitter collection failed @%s: %s", username, exc)
        return []


async def search_twitter_keyword(
    query: str,
    bearer_token: str,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Search recent tweets by keyword (last 7 days on free tier)."""
    if not bearer_token:
        return []

    try:
        async with httpx.AsyncClient(
            timeout=30,
            headers={"Authorization": f"Bearer {bearer_token}"},
        ) as client:
            r = await client.get(
                f"{_TWITTER_API}/2/tweets/search/recent",
                params={
                    "query": query,
                    "max_results": min(max(max_results, 10), 100),
                    "tweet.fields": "created_at,public_metrics,lang",
                },
            )
            if r.status_code != 200:
                return []
            return [
                p
                for p in (
                    _twitter_tweet_to_post(t, "")
                    for t in (r.json().get("data") or [])
                )
                if p
            ]
    except Exception as exc:
        logger.warning("Twitter keyword search failed: %s", exc)
        return []


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

def find_matched_entities(
    text: str, user_entities: list[str]
) -> list[str]:
    """Case-insensitive substring match — entity canonical name in post."""
    if not text or not user_entities:
        return []
    lowered = text.lower()
    return [e for e in user_entities if e and e.lower() in lowered]
