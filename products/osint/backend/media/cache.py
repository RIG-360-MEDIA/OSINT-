"""Tiny SQLite cache for image-verification results — persist-from-use.

Keyed by image URL. A verification (reverse-search ~15 s) runs once; every later
view of the same image reads the cached verdict. Survives container restart via a
mounted volume. No external DB dependency — keeps rigmedia self-contained.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any

_DB = os.environ.get("VERIFY_CACHE_DB", "/data/verify_cache.db")
_LOCK = threading.Lock()


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB) or ".", exist_ok=True)
    c = sqlite3.connect(_DB, timeout=10)
    c.execute(
        """CREATE TABLE IF NOT EXISTS verify_cache(
               image_url  TEXT PRIMARY KEY,
               dhash      TEXT,
               result     TEXT NOT NULL,
               created_at REAL NOT NULL)"""
    )
    return c


def get(image_url: str, max_age_days: float = 30.0) -> dict[str, Any] | None:
    """Return a cached result (with `_cached` flag) or None if absent/stale."""
    try:
        with _LOCK, _conn() as c:
            row = c.execute(
                "SELECT result, created_at FROM verify_cache WHERE image_url=?",
                (image_url,),
            ).fetchone()
    except sqlite3.Error:
        return None
    if not row:
        return None
    result, created = row
    if max_age_days and (time.time() - created) > max_age_days * 86400:
        return None
    data = json.loads(result)
    data["_cached"] = True
    data["_cached_at"] = round(created)
    return data


def put(image_url: str, result: dict[str, Any]) -> None:
    """Store (or refresh) a verification result. Best-effort — never raises."""
    try:
        with _LOCK, _conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO verify_cache(image_url, dhash, result, created_at) "
                "VALUES(?, ?, ?, ?)",
                (image_url, result.get("dhash"), json.dumps(result, default=str), time.time()),
            )
            c.commit()
    except sqlite3.Error:
        pass
