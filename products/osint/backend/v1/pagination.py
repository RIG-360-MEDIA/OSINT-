"""Opaque, tamper-evident keyset cursors for /v1 list endpoints.

A cursor encodes the last row's (sort_key, id) so the next page is a keyset
seek — stable under inserts, unlike OFFSET. The value is base64 of a tiny JSON
blob; any corruption/tampering fails closed with a 400 rather than silently
returning wrong data.

`sort_key` is whatever column the caller ORDERs BY, and it is NOT published_at:
the article feed pages on collected_at, list_scoped_stories on importance_score.
These functions are positional and untyped, so applying a cursor to the wrong
column would fail silently — the caller is responsible for pairing the key it
encodes with the column it compares.
"""
from __future__ import annotations

import base64
import json
from typing import Any

from .errors import bad_request


def encode_cursor(sort_key: Any, row_id: Any) -> str:
    """Encode (sort_key, id) — sort_key being the ORDER BY column of the CALLER's
    query (collected_at for articles, importance_score for stories), not published_at."""
    payload = {
        "t": sort_key.isoformat() if hasattr(sort_key, "isoformat") else str(sort_key),
        "i": str(row_id),
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str | None) -> tuple[str, str] | None:
    """Return (sort_key_str, id) as TWO STRINGS, or None if no cursor. 400 if malformed.

    The caller must coerce sort_key to the real column type before binding it
    (datetime for collected_at, float for importance_score) — asyncpg resolves the
    param type from the comparison and rejects a bare str."""
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
