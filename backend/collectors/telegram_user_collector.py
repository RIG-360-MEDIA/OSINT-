"""
Telegram user-account collector (MTProto via Telethon).

The Bot API cannot read public channels a bot isn't a member of. For
read-only surveillance of government / political channels we cannot join,
we sign in as a user account (one-time phone + SMS code produces a
StringSession) and use MTProto to iterate channel history.

All functions return the same post-dict shape the bot-based collector
produces, so `social_task._process_monitor_posts` works with either
source interchangeably.

Rate-limit & error handling:
  - FloodWaitError → log wait seconds, return what we have so far.
  - ChannelPrivateError / UsernameNotOccupiedError → log, return [].
  - Any other exception → log, return [].
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def collect_telegram_channel_as_user(
    channel_username: str,
    api_id: int,
    api_hash: str,
    session_string: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Fetch the most recent `limit` posts from a public Telegram channel
    via the signed-in user account.

    The account does not need to follow or be a member of the channel —
    Telegram's MTProto layer allows any user to read any channel whose
    `username` is resolvable (i.e. public).
    """
    if not session_string or not api_id or not api_hash:
        return []

    # Lazy import so the module loads cheaply when Telegram is disabled.
    from telethon import TelegramClient
    from telethon.errors import (
        ChannelPrivateError,
        FloodWaitError,
        UsernameInvalidError,
        UsernameNotOccupiedError,
    )
    from telethon.sessions import StringSession

    posts: list[dict[str, Any]] = []
    try:
        async with TelegramClient(
            StringSession(session_string), api_id, api_hash
        ) as client:
            try:
                channel = await client.get_entity(channel_username)
            except (
                ValueError,
                UsernameInvalidError,
                UsernameNotOccupiedError,
                ChannelPrivateError,
            ) as exc:
                logger.warning(
                    "Telegram(user): cannot resolve @%s — %s",
                    channel_username,
                    exc,
                )
                return []

            try:
                async for msg in client.iter_messages(channel, limit=limit):
                    post = _message_to_post(msg, channel_username)
                    if post:
                        posts.append(post)
            except FloodWaitError as exc:
                logger.warning(
                    "Telegram(user): flood wait %ss on @%s — "
                    "returning %d partial posts",
                    exc.seconds,
                    channel_username,
                    len(posts),
                )

    except FloodWaitError as exc:
        logger.warning(
            "Telegram(user) flood wait %ss during connect to @%s",
            exc.seconds,
            channel_username,
        )
    except Exception as exc:
        logger.warning(
            "Telegram(user) collection failed for @%s: %s",
            channel_username,
            exc,
        )

    return posts


def _message_to_post(
    msg: Any, channel_username: str
) -> dict[str, Any] | None:
    """Translate a Telethon Message into the unified social-post shape."""
    text = msg.message or getattr(msg, "text", None) or ""
    if not text:
        return None

    forwarded_from = ""
    fwd = getattr(msg, "forward", None)
    if fwd:
        fwd_chat = getattr(fwd, "chat", None)
        if fwd_chat is not None:
            forwarded_from = getattr(fwd_chat, "title", "") or ""
        elif getattr(fwd, "from_name", None):
            forwarded_from = fwd.from_name

    has_doc = getattr(msg, "document", None) is not None
    doc_id: str | None = None
    if has_doc and msg.document is not None:
        doc_id = str(msg.document.id)

    posted_at = msg.date.isoformat() if getattr(msg, "date", None) else None

    return {
        "platform": "telegram",
        "platform_post_id": str(msg.id),
        "author_username": channel_username,
        "post_text": text[:3000],
        "post_url": f"https://t.me/{channel_username}/{msg.id}",
        "forward_count": int(getattr(msg, "forwards", 0) or 0),
        "forwarded_from": forwarded_from,
        "has_document": has_doc,
        "document_url": doc_id,
        "posted_at": posted_at,
    }
