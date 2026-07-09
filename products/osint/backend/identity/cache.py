"""SQLite cache for identity-footprint results — persist-from-use.

A footprint (maigret across hundreds of sites) is expensive; run once per selector,
serve every later view from cache. Survives restart via a mounted volume.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any

_DB = os.environ.get("IDENT_CACHE_DB", "/data/identity_cache.db")
_LOCK = threading.Lock()


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB) or ".", exist_ok=True)
    c = sqlite3.connect(_DB, timeout=10)
    c.execute(
        """CREATE TABLE IF NOT EXISTS footprint_cache(
               selector   TEXT NOT NULL,
               top_sites  INTEGER NOT NULL,
               result     TEXT NOT NULL,
               created_at REAL NOT NULL,
               PRIMARY KEY (selector, top_sites))"""
    )
    return c


def get(selector: str, top_sites: int, max_age_days: float = 7.0) -> dict[str, Any] | None:
    try:
        with _LOCK, _conn() as c:
            row = c.execute(
                "SELECT result, created_at FROM footprint_cache WHERE selector=? AND top_sites=?",
                (selector, top_sites),
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


def put(selector: str, top_sites: int, result: dict[str, Any]) -> None:
    try:
        with _LOCK, _conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO footprint_cache(selector, top_sites, result, created_at) "
                "VALUES(?, ?, ?, ?)",
                (selector, top_sites, json.dumps(result, default=str), time.time()),
            )
            c.commit()
    except sqlite3.Error:
        pass
