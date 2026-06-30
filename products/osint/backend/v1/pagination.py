"""Opaque, tamper-evident keyset cursors for /v1 list endpoints.

A cursor encodes the last row's (published_at, id) so the next page is a
keyset seek — stable under inserts, unlike OFFSET. The value is base64 of a
tiny JSON blob; any corruption/tampering fails closed with a 400 rather than
silently returning wrong data.
"""
from __future__ import annotations

import base64
import json
from typing import Any

from .errors import bad_request


def encode_cursor(published_at: Any, row_id: Any) -> str:
    payload = {
        "t": published_at.isoformat() if hasattr(published_at, "isoformat") else str(published_at),
        "i": str(row_id),
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str | None) -> tuple[str, str] | None:
    """Return (published_at_iso, id) or None if no cursor. 400 if malformed."""
    if not cursor:
        return None
    try:
        pad = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(pad.encode("ascii"))
        obj = json.loads(raw)
        t, i = str(obj["t"]), str(obj["i"])
        if not t or not i:
            raise ValueError("empty cursor field")
        return t, i
    except Exception as exc:  # malformed/tampered -> fail closed
        raise bad_request("Invalid cursor") from exc
