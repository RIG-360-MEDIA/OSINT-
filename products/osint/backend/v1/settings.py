"""Gateway-local configuration.

Read directly from the environment (mirroring auth/middleware.py's handling of
the JWT secret) rather than the shared Settings dataclass, so the gateway is
self-contained and adding it never risks the rest of the app's boot.

The key-hash secret is fail-closed in production: the gateway refuses to run
without it, but the dashboard/app boots fine even before it's configured.
"""
from __future__ import annotations

import os

# Default to 'production' so a host that simply forgot to set the env var
# fails CLOSED (refuses the dev fallback secret) instead of silently using a
# well-known key. Local dev must set OSINT_ENVIRONMENT=development explicitly.
ENVIRONMENT: str = os.getenv("OSINT_ENVIRONMENT", os.getenv("ENVIRONMENT", "production")).lower()

# HMAC secret that hashes raw API keys. NEVER commit a real value.
_HASH_SECRET: str = os.getenv("OSINT_APIKEY_HASH_SECRET", "")

# Defaults; per-key overrides live in analytics.api_keys.
DEFAULT_RATE_LIMIT_PER_MIN: int = int(os.getenv("OSINT_V1_RATE_LIMIT", "120"))

# Pagination guard rails — hard caps the client cannot exceed.
DEFAULT_PAGE_SIZE: int = 20
MAX_PAGE_SIZE: int = 100

# Live sentiment/analytics windows.
MAX_WINDOW_DAYS: int = 90
DEFAULT_WINDOW_DAYS: int = 7

# A fixed, obviously-insecure secret used ONLY in non-production when the real
# secret is unset, so local tests can run. Production raises instead.
_DEV_FALLBACK_SECRET = "dev-insecure-apikey-secret-do-not-use-in-prod"


def hash_secret() -> str:
    """Return the HMAC secret, or fail closed in production if it's missing."""
    if _HASH_SECRET:
        return _HASH_SECRET
    if ENVIRONMENT == "production":
        raise RuntimeError(
            "OSINT_APIKEY_HASH_SECRET not configured — refusing to run the "
            "client /v1 API in production without a key-hash secret."
        )
    return _DEV_FALLBACK_SECRET
