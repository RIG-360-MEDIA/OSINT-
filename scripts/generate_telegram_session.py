"""
One-off interactive helper: sign into Telegram with a user account and
print a StringSession for the P17 Telegram user-account collector.

Usage (run OUTSIDE the container, in a normal terminal on the host):

    pip install telethon==1.36.0
    export TELEGRAM_API_ID=123456
    export TELEGRAM_API_HASH=your_api_hash_here
    python scripts/generate_telegram_session.py

Get API_ID and API_HASH from https://my.telegram.org/apps (free, takes
one minute — create a new "App" with any title; Platform: Desktop).

You will be prompted for:
  1. Phone number in international format, e.g. +919876543210
  2. Login code — Telegram sends it to your existing Telegram app
  3. Two-factor password (only if you've enabled 2FA on the account)

On success the script prints a long single-line STRING. Copy that
verbatim into `TELEGRAM_SESSION_STRING=...` in `infrastructure/.env`.

The session string is a long-lived credential tied to the user account;
treat it like a password. To revoke it, go to Telegram → Settings →
Devices → terminate the session named "Unknown device".
"""
from __future__ import annotations

import asyncio
import os
import sys


async def main() -> None:
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    if not api_id or not api_hash:
        print(
            "ERROR: set TELEGRAM_API_ID and TELEGRAM_API_HASH env vars "
            "before running.",
            file=sys.stderr,
        )
        print(
            "Get them from https://my.telegram.org/apps",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        print(
            "ERROR: telethon is not installed. Run: "
            "pip install telethon==1.36.0",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Connecting to Telegram…")
    async with TelegramClient(StringSession(), int(api_id), api_hash) as client:
        me = await client.get_me()
        username = getattr(me, "username", None) or "(no username)"
        phone = getattr(me, "phone", None) or "(no phone)"

        print()
        print("=" * 62)
        print(f"Logged in as: {me.first_name} @{username} ({phone})")
        print("=" * 62)
        print()
        print("Copy this ENTIRE line into TELEGRAM_SESSION_STRING "
              "in infrastructure/.env:")
        print()
        print(client.session.save())
        print()
        print("Then restart rig-backend:")
        print("  cd infrastructure && docker compose up -d "
              "--no-deps --force-recreate rig-backend")


if __name__ == "__main__":
    asyncio.run(main())
