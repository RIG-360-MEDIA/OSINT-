"""API key generation, hashing, and well-formedness checks.

Security model:
  * The raw key is shown to the client exactly once, at creation, and never
    stored. We persist only ``HMAC-SHA256(server_secret, raw_key)`` (hex), so
    a database dump cannot recover a usable key.
  * Lookup is by hash equality (indexed, O(1)). Forging a matching 256-bit
    HMAC without the server secret is infeasible, so a constant-time string
    compare on the hash buys nothing here — the secrecy is in the secret.
  * Keys are opaque, URL-safe, and prefixed so logs/leaks are recognisable
    and revocable: ``rig_live_…`` (production) / ``rig_test_…`` (sandbox).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

LIVE_PREFIX = "rig_live_"
TEST_PREFIX = "rig_test_"

# token_urlsafe(32) yields ~43 url-safe chars; require a healthy minimum so a
# truncated/garbage string can never accidentally validate.
_RANDOM_BYTES = 32
_MIN_BODY_LEN = 40
# Display fragment length: the prefix plus 6 chars of randomness.
_PREFIX_DISPLAY_EXTRA = 6


def generate_key(sandbox: bool = False) -> str:
    """Return a fresh opaque key. Cryptographically random; show once."""
    prefix = TEST_PREFIX if sandbox else LIVE_PREFIX
    return prefix + secrets.token_urlsafe(_RANDOM_BYTES)


def is_well_formed(raw: object) -> bool:
    """True only for a string with a known prefix and sufficient entropy."""
    if not isinstance(raw, str):
        return False
    if raw.startswith(LIVE_PREFIX):
        body = raw[len(LIVE_PREFIX):]
    elif raw.startswith(TEST_PREFIX):
        body = raw[len(TEST_PREFIX):]
    else:
        return False
    # Body must be long enough and contain only url-safe base64 chars.
    if len(body) < _MIN_BODY_LEN:
        return False
    return all(c.isalnum() or c in "-_" for c in body)


def is_sandbox(raw: str) -> bool:
    """True if the key is a sandbox/test key."""
    return raw.startswith(TEST_PREFIX)


def hash_key(raw: str, secret: str) -> str:
    """HMAC-SHA256(secret, raw) as hex. Deterministic for a given secret."""
    return hmac.new(secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()


def derive_webhook_secret(webhook_id: str, secret: str) -> str:
    """Deterministic per-webhook signing secret, derived not stored.

    The delivery worker recomputes this from the (immutable) webhook id, so the
    raw signing secret never sits at rest in the DB. Domain-separated from key
    hashing by the 'webhook:' prefix.
    """
    mac = hmac.new(secret.encode("utf-8"), f"webhook:{webhook_id}".encode("utf-8"), hashlib.sha256)
    return "whsec_" + mac.hexdigest()


def prefix_of(raw: str) -> str:
    """Non-secret display fragment, e.g. 'rig_live_AbC123' — safe to store/show."""
    if raw.startswith(LIVE_PREFIX):
        plen = len(LIVE_PREFIX)
    elif raw.startswith(TEST_PREFIX):
        plen = len(TEST_PREFIX)
    else:
        plen = 0
    return raw[: plen + _PREFIX_DISPLAY_EXTRA]
