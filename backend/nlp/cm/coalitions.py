"""
Coalition resolution for CM Page.

Maps a (state, party) pair to a party_kind in {ruling, opposition, neutral}
using the cm_coalitions table seeded in migration 029. Loaded once per
process and refreshed on a TTL — coalition realignments are rare but the
process may run for days so we don't want to be permanently stale.

Anything not in cm_coalitions resolves to 'neutral' rather than raising,
because the press / civil-society / unaligned-party content is real and
should not be dropped just because the table is incomplete.
"""
from __future__ import annotations

import logging
import time
from threading import RLock

from sqlalchemy import text

from backend.database import get_db

logger = logging.getLogger(__name__)

_RELOAD_S = 600
_loaded_at: float = 0.0
_map: dict[tuple[str, str], str] = {}
_lock = RLock()


async def _load() -> None:
    global _loaded_at, _map
    new_map: dict[tuple[str, str], str] = {}
    try:
        async with get_db() as db:
            rows = (
                await db.execute(text("SELECT state, party, coalition FROM cm_coalitions"))
            ).all()
        for r in rows:
            new_map[(r.state, r.party.upper())] = r.coalition
    except Exception as exc:
        logger.warning("cm_coalitions load failed (%s); keeping previous map", exc)
        return
    with _lock:
        _map = new_map
        _loaded_at = time.time()


async def party_kind(state: str | None, party: str | None) -> str:
    """Return 'ruling' / 'opposition' / 'neutral' for the given party in
    the given state. Defaults to 'neutral' when state or party is unknown
    or the row is not in cm_coalitions."""
    if not state or not party:
        return "neutral"
    if time.time() - _loaded_at > _RELOAD_S:
        await _load()
    return _map.get((state, party.upper()), "neutral")


async def parties_for(state: str, coalition: str) -> list[str]:
    """List all parties tagged as the given coalition in the given state.
    Used when scoring stance to look up which parties count as 'ruling' /
    'opposition' for the user's selected state."""
    if time.time() - _loaded_at > _RELOAD_S:
        await _load()
    with _lock:
        return [
            party
            for (s, party), c in _map.items()
            if s == state and c == coalition
        ]


def coalition_summary() -> dict[str, dict[str, list[str]]]:
    """Diagnostic: returns {state: {coalition: [parties]}}."""
    out: dict[str, dict[str, list[str]]] = {}
    with _lock:
        for (s, p), c in _map.items():
            out.setdefault(s, {}).setdefault(c, []).append(p)
    return out
