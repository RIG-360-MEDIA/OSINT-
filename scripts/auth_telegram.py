"""
One-shot Telegram MTProto authentication.

Run this once (interactively) whenever the existing TELEGRAM_SESSION_STRING in
.env stops working — typically because Telegram revoked the session, you logged
out from another device, or the credential was rotated.

Run from repo root:

    docker exec -it rig-backend python scripts/auth_telegram.py

The -it flag is required so the script can prompt for your phone number, the
login code Telegram texts you, and (if you have 2FA enabled) your password.

At the end it prints a fresh StringSession. Paste it into .env as

    TELEGRAM_SESSION_STRING=<the long string>

then restart the backend container:

    docker compose -f infrastructure/docker-compose.yml restart rig-backend

Re-run this script any time the collector starts logging
'StringSession revoked' or returning zero posts for all monitored channels.

The session string IS your Telegram identity — never share it, never commit it.
"""
from __future__ import annotations

import asyncio
import os
import sys
from getpass import getpass

from telethon import TelegramClient
from telethon.errors import (
    PasswordHashInvalidError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession


def _read_env() -> tuple[int, str]:
    """Read API ID and hash from environment. Exit with a useful message if missing."""
    api_id_raw = (os.getenv("TELEGRAM_API_ID") or "").strip()
    api_hash = (os.getenv("TELEGRAM_API_HASH") or "").strip()

    if not api_id_raw or not api_hash:
        sys.exit(
            "ERROR: TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in .env "
            "before running this script. Get them at https://my.telegram.org "
            "→ API development tools."
        )

    try:
        api_id = int(api_id_raw)
    except ValueError:
        sys.exit(f"ERROR: TELEGRAM_API_ID is not an integer: {api_id_raw!r}")

    return api_id, api_hash


def _prompt_phone() -> str:
    print()
    print("Enter your Telegram phone number in international format.")
    print("Example: +919876543210  (include the +country code, no spaces)")
    phone = input("Phone: ").strip()
    if not phone.startswith("+") or len(phone) < 8:
        sys.exit("ERROR: phone must start with + and include country code.")
    return phone


def _prompt_code() -> str:
    print()
    print("Telegram is texting a 5-digit login code to that number.")
    print("Look for a message from the 'Telegram' service inside the app.")
    code = input("Login code: ").strip()
    if not code.isdigit():
        sys.exit("ERROR: login code should be digits only.")
    return code


def _prompt_2fa() -> str:
    print()
    print("Two-step verification is enabled on this account.")
    print("Enter your Telegram cloud password (it will not be echoed).")
    return getpass("2FA password: ")


async def _authenticate() -> str:
    api_id, api_hash = _read_env()

    print("=" * 64)
    print("RIG Surveillance — Telegram session refresh")
    print("=" * 64)
    print(f"Using TELEGRAM_API_ID = {api_id}")

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()

    if await client.is_user_authorized():
        # The empty StringSession() passed in cannot already be authorized,
        # so this branch is essentially unreachable — but defensive.
        print("Already authorized. Printing session string.")
        return client.session.save()

    phone = _prompt_phone()
    try:
        await client.send_code_request(phone)
    except Exception as exc:
        await client.disconnect()
        sys.exit(f"ERROR: failed to send code: {type(exc).__name__}: {exc}")

    code = _prompt_code()
    try:
        await client.sign_in(phone=phone, code=code)
    except SessionPasswordNeededError:
        password = _prompt_2fa()
        try:
            await client.sign_in(password=password)
        except PasswordHashInvalidError:
            await client.disconnect()
            sys.exit("ERROR: 2FA password rejected by Telegram.")
    except PhoneCodeInvalidError:
        await client.disconnect()
        sys.exit("ERROR: login code rejected. Re-run the script and try again.")
    except Exception as exc:
        await client.disconnect()
        sys.exit(f"ERROR: sign-in failed: {type(exc).__name__}: {exc}")

    if not await client.is_user_authorized():
        await client.disconnect()
        sys.exit("ERROR: sign-in completed but session is not authorized.")

    me = await client.get_me()
    session_string = client.session.save()
    await client.disconnect()

    print()
    print("=" * 64)
    print(f"Logged in as: {me.first_name or ''} {me.last_name or ''} "
          f"(@{me.username or '—'})  id={me.id}")
    print("=" * 64)
    return session_string


def main() -> None:
    try:
        session_string = asyncio.run(_authenticate())
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(130)

    print()
    print("Copy the line BETWEEN the BEGIN and END markers into .env as:")
    print("    TELEGRAM_SESSION_STRING=<paste here>")
    print()
    print("----- BEGIN SESSION STRING -----")
    print(session_string)
    print("------ END SESSION STRING ------")
    print()
    print("Then restart the backend container:")
    print("    docker compose -f infrastructure/docker-compose.yml "
          "restart rig-backend")
    print()
    print("Verify the new session works by tailing logs after restart:")
    print("    docker logs -f rig-backend | grep -i telegram")


if __name__ == "__main__":
    main()
