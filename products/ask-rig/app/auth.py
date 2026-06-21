"""Password + token primitives — stdlib only (pbkdf2 + sha256), no heavy deps.

Pure functions, fully unit-tested. Passwords are pbkdf2-hashed with a per-user
salt; bearer tokens are random and stored only as their sha256 (so a DB leak
doesn't expose usable tokens).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

_ITERATIONS = 120_000


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Return (hex_hash, salt). Generates a salt if none supplied."""
    if not password:
        raise ValueError("password must not be empty")
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), _ITERATIONS)
    return dk.hex(), salt


def verify_password(password: str, pwd_hash: str, salt: str) -> bool:
    calc, _ = hash_password(password, salt)
    return hmac.compare_digest(calc, pwd_hash)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def new_token() -> tuple[str, str]:
    """Return (raw_token, token_hash). Show raw once; store only the hash."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)
