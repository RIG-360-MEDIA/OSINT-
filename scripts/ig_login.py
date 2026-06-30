#!/usr/bin/env python3
"""
One-time Instagram login → settings file generator (run LOCALLY on a residential box).

WHY: instagrapi's strict mobile endpoints (hashtag / comments / location / stories)
require a FULL username+password login to mint the mobile bearer token. A sessionid
cookie alone is a "soft" login that those endpoints reject with `login_required`.

This script does the full login ONCE, then dumps the authenticated session (incl. the
minted bearer + device fingerprint) to a JSON settings file. The relay then loads that
file with cl.load_settings() — so NO password ever lives in the backend or in env.

SECURITY:
  - Run this on the residential relay box, not on Hetzner (datacenter is IP-blocked).
  - Use a BURNER Instagram account — full login is ban-prone; never a personal one.
  - The password is read via getpass (never echoed, never stored, never an argv).
  - The output file (ig_session.json) contains the bearer — treat it like a secret.

USAGE:
    pip install instagrapi
    python scripts/ig_login.py                 # prompts for user + password
    python scripts/ig_login.py --out /secrets/ig_session.json

    # then point the relay at it:
    export IG_SETTINGS_FILE=/secrets/ig_session.json

If Instagram issues a 2FA code or a challenge, instagrapi will prompt for it here.
Re-run only when the session dies (login_required on previously-working calls).
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an instagrapi session settings file.")
    parser.add_argument("--out", default="ig_session.json", help="output settings path")
    parser.add_argument("--username", default=None, help="IG username (else prompted)")
    parser.add_argument("--verify-tag", default="india", help="hashtag to verify the session unlocks discovery")
    args = parser.parse_args()

    try:
        from instagrapi import Client
        from instagrapi.exceptions import TwoFactorRequired, ChallengeRequired
    except ImportError:
        print("instagrapi not installed — run: pip install instagrapi", file=sys.stderr)
        return 1

    username = args.username or input("Instagram username (burner): ").strip()
    password = getpass.getpass("Instagram password (hidden): ")

    cl = Client()
    cl.delay_range = [2, 5]  # be gentle

    # ── full login (mints the mobile bearer the strict endpoints need) ──
    try:
        cl.login(username, password)
    except TwoFactorRequired:
        code = input("2FA code: ").strip()
        cl.login(username, password, verification_code=code)
    except ChallengeRequired:
        print(
            "Instagram issued a challenge. Approve the login in the IG app / email, "
            "then re-run this script.",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(f"Login failed: {exc}", file=sys.stderr)
        return 1

    print(f"Login OK — user_id={cl.user_id}, bearer minted.")

    # ── verify the session actually unlocks the gated discovery endpoints ──
    try:
        medias = cl.hashtag_medias_top_v1(args.verify_tag.lstrip("#"), amount=2)
        print(f"Verify: hashtag '#{args.verify_tag}' returned {len(medias)} posts "
              f"-> discovery endpoints UNLOCKED.")
    except Exception as exc:
        print(f"Verify WARNING: hashtag fetch failed ({exc}). "
              f"Login succeeded but discovery may still be gated — check account standing.",
              file=sys.stderr)

    # ── dump the authenticated session (bearer + device fingerprint) ──
    out = Path(args.out)
    cl.dump_settings(out)
    print(f"\nSession written to: {out.resolve()}")
    print("Point the relay at it:  export IG_SETTINGS_FILE=" + str(out.resolve()))
    print("Treat this file as a SECRET — it contains the mobile bearer token.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
