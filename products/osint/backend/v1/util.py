"""Small shared helpers for /v1."""
from __future__ import annotations

import uuid


def as_uuid(value: object) -> str | None:
    """Return the canonical UUID string if ``value`` is a valid UUID, else None.

    Used to validate path/query ids before they reach a ``CAST(... AS uuid)`` —
    a malformed id is rejected by the route (as 404/400) rather than raising a
    DB error.
    """
    if not isinstance(value, str):
        return None
    try:
        return str(uuid.UUID(value.strip()))
    except (ValueError, AttributeError):
        return None
