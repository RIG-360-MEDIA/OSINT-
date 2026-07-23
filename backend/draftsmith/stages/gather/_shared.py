"""backend.draftsmith.stages.gather._shared — small helpers shared by the
gather-stage adapters (social.py / web.py / wiki.py).

Not a stage itself and not re-exported anywhere — each adapter imports it
directly (`from backend.draftsmith.stages.gather._shared import ...`), same
as db/_common.py is a private helper for the db/ package. Deliberately has
no I/O of its own beyond string/hash/parsing utilities.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

from backend.draftsmith.models import TimeWindow

# Defensive ceiling on one evidence item's frozen text snapshot. NOT the
# BRIEF-selection char cap (config.CHAR_CAPS — that's the rank stage's job
# once an item is actually selected); this only stops a pathological page or
# thread from bloating a draft_evidence row before rank gets a chance to trim.
MAX_SNAPSHOT_CHARS = 20_000


def make_source_id(prefix: str, raw: str) -> str:
    """Stable citation handle: `<prefix>_<sha1(raw)[:16]>`.

    Hash-derived rather than counter-derived so re-running gather for the
    same job (retry, resumed lease) reproduces the same source_id for the
    same underlying item — save_evidence's ON CONFLICT (job_id, source_id)
    then updates the row in place instead of duplicating it.
    """
    if not raw:
        raise ValueError("make_source_id: raw is empty")
    digest = hashlib.sha1(raw.encode("utf-8", "ignore")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """Best-effort ISO-8601 string -> aware datetime. None on anything
    unparsable or empty — EvidenceItem.published_at is Optional, so a bad
    timestamp is never worth raising over."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def domain_of(url: Optional[str]) -> Optional[str]:
    """Lowercased host, minus a leading 'www.'. None if `url` is empty or
    doesn't parse to a host."""
    if not url:
        return None
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return None
    if not host:
        return None
    return host[4:] if host.startswith("www.") else host


def clip_text(text: str, cap: int = MAX_SNAPSHOT_CHARS) -> str:
    """Hard-cap a snapshot's length. A no-op for anything under `cap`."""
    return text if len(text) <= cap else text[:cap]


def resolve_time_window(window: TimeWindow) -> tuple[datetime, Optional[datetime]]:
    """QueryPlan's relative `TimeWindow` ("N days ago") -> absolute aware UTC
    (since, until) bounds for a SQL `published_at >= since AND (until IS NULL
    OR published_at <= until)` filter. `until` is None when the plan leaves
    the window open-ended at "now" (the common case — most-recent coverage).
    Used by the warehouse-backed adapters (articles, story facts, YouTube
    clips warehouse); the on-demand social/web/wiki adapters have no
    analogous published-time filter to apply here.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=max(0, window.from_days_ago))
    until: Optional[datetime] = None
    if window.to_days_ago is not None:
        until = now - timedelta(days=max(0, window.to_days_ago))
    return since, until
