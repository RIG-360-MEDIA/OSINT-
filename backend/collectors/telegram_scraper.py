"""
Telegram scraper via Telethon user session (no bot, no channel membership).

Raw collection only — no extraction, no sentiment, no entity matching.
Returns the common social post shape defined in social_scraper.py.

Reads any PUBLIC channel's full history directly through an MTProto user
session — richer than the Bot API (which is forward-only polling and needs
the bot added to each channel). Gives view counts, forward counts, and the
forwarded-from source channel — real reach + propagation signal for OSINT.

Setup (one-time — credentials already provisioned in infrastructure/.env):
    1. Get API_ID + API_HASH from https://my.telegram.org/apps
       (no reCAPTCHA, no approval wall — instant).
    2. Generate a session string once:
       python scripts/generate_telegram_session.py

    export TELEGRAM_API_ID=<api_id>
    export TELEGRAM_API_HASH=<api_hash>
    export TELEGRAM_SESSION_STRING=<session_string>

Usage:
    scraper = TelegramScraper()
    posts = await scraper.channel("durov", limit=20)
    posts = await scraper.channel("durov", limit=50, min_id=12345)   # incremental
    posts = await scraper.search_channel("durov", "India", limit=20)
    info  = await scraper.channel_info("durov")
"""
from __future__ import annotations

import logging
import os
from datetime import timezone
from typing import Any

logger = logging.getLogger(__name__)

_API_ID = int(os.getenv("TELEGRAM_API_ID", "0") or "0")
_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
_SESSION = os.getenv("TELEGRAM_SESSION_STRING", "")

_MEDIA_PLACEHOLDER = "this message couldn't be displayed"


# ── normaliser ────────────────────────────────────────────────────────────────

def _msg_to_post(msg: Any, channel_username: str, channel_title: str | None) -> dict[str, Any] | None:
    """Convert a Telethon Message to the common post shape. None if empty/placeholder."""
    text = (msg.text or getattr(msg, "caption", None) or "").strip()
    if not text:
        return None
    # Telegram's copyright-takedown placeholder — not real content
    if text.lower().startswith("__") and _MEDIA_PLACEHOLDER in text.lower():
        return None

    handle = channel_username.lstrip("@")

    media_urls: list[str] = []
    if msg.media is not None:
        # file_id placeholder — actual download deferred to a storage layer
        media_urls.append(f"tg://file/{msg.id}")

    forwarded_from = None
    if msg.forward is not None:
        chat = getattr(msg.forward, "chat", None)
        if chat is not None:
            forwarded_from = getattr(chat, "title", None) or getattr(chat, "username", None)

    replies = None
    if getattr(msg, "replies", None) is not None:
        replies = msg.replies.replies

    return {
        "platform": "telegram",
        "platform_post_id": str(msg.id),
        "author_username": handle,
        "author_name": channel_title,
        "post_text": text[:4000],
        "post_url": f"https://t.me/{handle}/{msg.id}",
        "posted_at": msg.date.astimezone(timezone.utc).isoformat(),
        "likes": None,
        "comments": replies,
        "shares": msg.forwards or None,
        "upvotes": None,
        "has_media": msg.media is not None,
        "media_urls": media_urls,
        "raw": {
            "id": msg.id,
            "views": msg.views,
            "forwards": msg.forwards,
            "replies": replies,
            "forwarded_from": forwarded_from,
            "grouped_id": msg.grouped_id,
            "edit_date": msg.edit_date.isoformat() if msg.edit_date else None,
        },
    }


# ── scraper class ─────────────────────────────────────────────────────────────

class TelegramScraper:
    """
    Async Telegram channel scraper using a Telethon user session.

    Each call opens and closes its own client (Telethon clients are not safe
    to share across event loops / long-lived in a Celery prefork worker).
    For batch collection, pass several channels to collect_many().
    """

    def __init__(
        self,
        api_id: int = _API_ID,
        api_hash: str = _API_HASH,
        session_string: str = _SESSION,
    ) -> None:
        self._api_id = api_id
        self._api_hash = api_hash
        self._session_string = session_string

    def _check(self) -> None:
        if not self._api_id or not self._api_hash or not self._session_string:
            raise RuntimeError(
                "Set TELEGRAM_API_ID, TELEGRAM_API_HASH and "
                "TELEGRAM_SESSION_STRING env vars."
            )

    def _client(self):
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        return TelegramClient(
            StringSession(self._session_string), self._api_id, self._api_hash
        )

    # ── public methods ────────────────────────────────────────────────────────

    async def channel(
        self,
        username: str,
        *,
        limit: int = 25,
        min_id: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Fetch recent posts from a public channel.
        min_id: only messages newer than this ID (incremental collection —
                set to the last seen ID to avoid re-processing).
        """
        self._check()
        posts: list[dict[str, Any]] = []
        try:
            async with self._client() as client:
                try:
                    entity = await client.get_entity(username)
                except Exception as exc:
                    logger.warning("Telegram: can't resolve %s: %s", username, exc)
                    return []
                title = getattr(entity, "title", None)
                async for msg in client.iter_messages(entity, limit=limit, min_id=min_id):
                    post = _msg_to_post(msg, username, title)
                    if post:
                        posts.append(post)
        except Exception:
            logger.exception("Telegram channel failed (%s)", username)
        return posts

    async def search_channel(
        self,
        username: str,
        query: str,
        *,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """Search within a single public channel for a keyword."""
        self._check()
        posts: list[dict[str, Any]] = []
        try:
            async with self._client() as client:
                try:
                    entity = await client.get_entity(username)
                except Exception as exc:
                    logger.warning("Telegram: can't resolve %s: %s", username, exc)
                    return []
                title = getattr(entity, "title", None)
                async for msg in client.iter_messages(entity, limit=limit, search=query):
                    post = _msg_to_post(msg, username, title)
                    if post:
                        posts.append(post)
        except Exception:
            logger.exception("Telegram search_channel failed (%s, q=%r)", username, query)
        return posts

    async def channel_info(self, username: str) -> dict[str, Any] | None:
        """Fetch channel metadata: title, subscriber count, description."""
        self._check()
        try:
            from telethon.tl.functions.channels import GetFullChannelRequest
            async with self._client() as client:
                entity = await client.get_entity(username)
                full = await client(GetFullChannelRequest(entity))
                return {
                    "platform": "telegram",
                    "username": getattr(entity, "username", username.lstrip("@")),
                    "title": getattr(entity, "title", None),
                    "subscribers": getattr(full.full_chat, "participants_count", None),
                    "description": getattr(full.full_chat, "about", "") or "",
                    "verified": getattr(entity, "verified", False),
                    "id": entity.id,
                }
        except Exception:
            logger.exception("Telegram channel_info failed (%s)", username)
            return None

    async def collect_many(
        self,
        usernames: list[str],
        *,
        limit: int = 25,
        min_ids: dict[str, int] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Collect from several channels in a single client session (efficient —
        one connection for the whole batch). Returns {username: [posts]}.
        min_ids: optional per-channel incremental cursor.
        """
        self._check()
        min_ids = min_ids or {}
        out: dict[str, list[dict[str, Any]]] = {}
        try:
            async with self._client() as client:
                for username in usernames:
                    try:
                        entity = await client.get_entity(username)
                    except Exception as exc:
                        logger.warning("Telegram: can't resolve %s: %s", username, exc)
                        out[username] = []
                        continue
                    title = getattr(entity, "title", None)
                    posts: list[dict[str, Any]] = []
                    async for msg in client.iter_messages(
                        entity, limit=limit, min_id=min_ids.get(username, 0)
                    ):
                        post = _msg_to_post(msg, username, title)
                        if post:
                            posts.append(post)
                    out[username] = posts
        except Exception:
            logger.exception("Telegram collect_many failed")
        return out


# ── module-level singleton ────────────────────────────────────────────────────

_scraper: TelegramScraper | None = None


def get_scraper() -> TelegramScraper:
    global _scraper
    if _scraper is None:
        _scraper = TelegramScraper()
    return _scraper


# ── CLI smoke-test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    async def _smoke():
        s = TelegramScraper()

        print("--- @durov (4) ---")
        for p in await s.channel("durov", limit=4):
            line = f"  [{p['posted_at'][:10]}] v={p['raw']['views']} fwd={p['shares']}: {p['post_text'][:60]}"
            print(line.encode("ascii", "replace").decode())

        print("\n--- channel_info: durov ---")
        info = await s.channel_info("durov")
        if info:
            print(f"  {info['title']} — {info['subscribers']} subscribers, verified={info['verified']}")

        print("\n--- search @durov for 'India' (3) ---")
        for p in await s.search_channel("durov", "India", limit=3):
            line = f"  [{p['posted_at'][:10]}]: {p['post_text'][:65]}"
            print(line.encode("ascii", "replace").decode())

    asyncio.run(_smoke())
