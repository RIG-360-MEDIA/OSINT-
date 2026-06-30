"""
Twitter scraper via twscrape (cookie-based, no API key needed).

Raw collection only — no extraction, no sentiment, no entity matching.
Returns the common social post shape defined in social_scraper.py.

Setup (one-time):
    export TWITTER_USERNAME=pranavsingq6
    export TWITTER_AUTH_TOKEN=<auth_token cookie from x.com>
    export TWITTER_CT0=<ct0 cookie from x.com>
    export TWITTER_POOL_DB=/path/to/twscrape_pool.db   # optional, default=.twscrape.db

Usage:
    scraper = TwitterScraper()
    await scraper.init()
    posts = await scraper.search("India Modi", limit=20)
    posts = await scraper.user_tweets("narendramodi", limit=50)
    trends = await scraper.trends()
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_POOL_DB = os.getenv("TWITTER_POOL_DB", ".twscrape.db")
_USERNAME = os.getenv("TWITTER_USERNAME", "")
_AUTH_TOKEN = os.getenv("TWITTER_AUTH_TOKEN", "")
_CT0 = os.getenv("TWITTER_CT0", "")


# ── normaliser ───────────────────────────────────────────────────────────────

def _to_iso(dt: datetime | None) -> str:
    if dt is None:
        return datetime.now(timezone.utc).isoformat()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _normalise(tweet: Any) -> dict[str, Any]:
    """Convert a twscrape Tweet object to the common post shape."""
    user = tweet.user
    media_urls: list[str] = []
    has_media = False

    if tweet.media:
        for m in tweet.media.photos or []:
            media_urls.append(m.url)
            has_media = True
        for m in tweet.media.videos or []:
            if m.variants:
                media_urls.append(m.variants[0].url)
            has_media = True
        for m in tweet.media.animated or []:
            media_urls.append(m.videoUrl or "")
            has_media = True

    return {
        "platform": "twitter",
        "platform_post_id": str(tweet.id),
        "author_username": user.username if user else "unknown",
        "author_name": user.displayname if user else None,
        "post_text": (tweet.rawContent or "")[:4000],
        "post_url": tweet.url or f"https://x.com/i/web/status/{tweet.id}",
        "posted_at": _to_iso(tweet.date),
        "likes": tweet.likeCount,
        "comments": tweet.replyCount,
        "shares": tweet.retweetCount,
        "upvotes": None,
        "has_media": has_media,
        "media_urls": media_urls,
        "raw": {
            "quote_count": tweet.quoteCount,
            "view_count": tweet.viewCount,
            "lang": tweet.lang,
            "is_retweet": tweet.retweetedTweet is not None,
            "is_reply": tweet.inReplyToTweetId is not None,
            # twscrape returns hashtags as plain strings and mentions as objects;
            # be defensive in case either shape changes across versions.
            "hashtags": [getattr(h, "text", h) for h in (tweet.hashtags or [])],
            "mentions": [getattr(m, "username", m) for m in (tweet.mentionedUsers or [])],
        },
    }


# ── scraper class ─────────────────────────────────────────────────────────────

class TwitterScraper:
    """
    Thin async wrapper around twscrape.

    Call await scraper.init() before use.
    The account pool is persisted to TWITTER_POOL_DB so you only need
    to add the account once — subsequent init() calls are no-ops if the
    account already exists.
    """

    def __init__(
        self,
        pool_db: str = _POOL_DB,
        username: str = _USERNAME,
        auth_token: str = _AUTH_TOKEN,
        ct0: str = _CT0,
    ) -> None:
        self._pool_db = pool_db
        self._username = username
        self._auth_token = auth_token
        self._ct0 = ct0
        self._api: Any = None

    async def init(self) -> None:
        from twscrape import API, AccountsPool

        if not self._auth_token or not self._ct0:
            raise RuntimeError(
                "Set TWITTER_AUTH_TOKEN and TWITTER_CT0 env vars before using TwitterScraper."
            )

        pool = AccountsPool(self._pool_db)
        cookies = f"auth_token={self._auth_token}; ct0={self._ct0}"
        await pool.add_account(
            username=self._username or "rig_scraper",
            password="placeholder",
            email="placeholder@rig.local",
            email_password="placeholder",
            cookies=cookies,
        )
        # Do NOT call login_all() — programmatic login is Cloudflare-blocked on
        # datacenter IPs. Browser-extracted cookies are already valid; skip re-auth.
        self._api = API(pool)
        logger.info("TwitterScraper ready (pool_db=%s account=%s)", self._pool_db, self._username)

    def _check(self) -> None:
        if self._api is None:
            raise RuntimeError("Call await scraper.init() first.")

    # ── public methods ────────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        *,
        limit: int = 50,
        product: str = "Latest",
    ) -> list[dict[str, Any]]:
        """
        Search tweets. product='Latest' for chronological, 'Top' for algorithmic.
        Returns up to `limit` posts in common shape.
        """
        self._check()
        posts: list[dict[str, Any]] = []
        try:
            async for tweet in self._api.search(query, limit=limit):
                posts.append(_normalise(tweet))
        except Exception:
            logger.exception("twitter search failed (query=%r)", query)
        return posts

    async def user_tweets(
        self,
        username: str,
        *,
        limit: int = 50,
        include_replies: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Fetch recent tweets from a user's timeline.
        """
        self._check()
        posts: list[dict[str, Any]] = []
        try:
            user = await self._api.user_by_login(username)
            if user is None:
                logger.warning("twitter: user not found: %s", username)
                return []
            method = (
                self._api.user_tweets_and_replies
                if include_replies
                else self._api.user_tweets
            )
            async for tweet in method(user.id, limit=limit):
                posts.append(_normalise(tweet))
        except Exception:
            logger.exception("twitter user_tweets failed (username=%r)", username)
        return posts

    async def tweet_by_id(self, tweet_id: str) -> dict[str, Any] | None:
        """Fetch a single tweet by ID."""
        self._check()
        try:
            tweet = await self._api.tweet_details(int(tweet_id))
            return _normalise(tweet) if tweet else None
        except Exception:
            logger.exception("twitter tweet_by_id failed (id=%s)", tweet_id)
            return None

    async def trends(self, region: str = "india") -> list[dict[str, str]]:
        """
        Fetch Twitter trending topics by scraping trends24.in (no auth needed).

        region: "india", "worldwide", "united-states", "united-kingdom", etc.
                (any slug from trends24.in/<region>/)
        Returns list of {name, url} for the most recent trend window (~50 items).
        tweet_volume is not available (JS-rendered on trends24.in).
        """
        if region in ("world", "worldwide", "global"):
            target = "https://www.trends24.in/"
        else:
            target = f"https://www.trends24.in/{region}/"
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15,
                follow_redirects=True,
            ) as client:
                r = await client.get(target)
                r.raise_for_status()

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "html.parser")
            cards = soup.select("ol.trend-card__list")
            if not cards:
                logger.warning("trends24: no trend cards found for region=%s", region)
                return []

            results: list[dict[str, str]] = []
            for a in cards[0].select("li a.trend-link"):
                name = a.get_text(strip=True)
                url = a.get("href", f"https://x.com/search?q={name.replace(' ', '%20')}")
                if name:
                    results.append({"name": name, "tweet_volume": "", "url": url})
            return results
        except Exception:
            logger.exception("trends24 scrape failed (region=%s)", region)
            return []

    async def user_by_username(self, username: str) -> dict[str, Any] | None:
        """Fetch a user profile."""
        self._check()
        try:
            user = await self._api.user_by_login(username)
            if user is None:
                return None
            return {
                "platform": "twitter",
                "username": user.username,
                "display_name": user.displayname,
                "bio": user.rawDescription or "",
                "followers": user.followersCount,
                "following": user.friendsCount,
                "tweet_count": user.statusesCount,
                "verified": user.blue or user.verified,
                "profile_image_url": user.profileImageUrl,
                "created_at": _to_iso(user.created),
            }
        except Exception:
            logger.exception("twitter user_by_username failed (%r)", username)
            return None


# ── convenience: module-level singleton ───────────────────────────────────────

_scraper: TwitterScraper | None = None


async def get_scraper() -> TwitterScraper:
    """Return the module-level singleton, initialised on first call."""
    global _scraper
    if _scraper is None:
        _scraper = TwitterScraper()
        await _scraper.init()
    return _scraper


# ── CLI smoke-test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio, json, sys

    async def _smoke():
        s = TwitterScraper(
            pool_db=".twscrape_test.db",
            username=sys.argv[1] if len(sys.argv) > 1 else _USERNAME,
            auth_token=_AUTH_TOKEN,
            ct0=_CT0,
        )
        await s.init()

        print("\n--- search: India news ---")
        posts = await s.search("India news", limit=3)
        for p in posts:
            print(f"  @{p['author_username']}: {p['post_text'][:80]}".encode("ascii", "replace").decode())

        print("\n--- user_tweets: narendramodi ---")
        posts = await s.user_tweets("narendramodi", limit=3)
        for p in posts:
            print(f"  {p['posted_at'][:10]}: {p['post_text'][:80]}".encode("ascii", "replace").decode())

        print("\n--- trends (India) ---")
        trends = await s.trends(woeid=23424848)
        for t in trends[:5]:
            print(f"  {t['name']} ({t['tweet_volume']} tweets)".encode("ascii", "replace").decode())

    asyncio.run(_smoke())
