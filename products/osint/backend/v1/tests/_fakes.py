"""Shared fakes for the /v1 no-DB test suite.

Every query function in queries.py takes ``db`` as a parameter and only calls
``await db.execute(...)`` / ``.commit()`` / ``.begin()``. These fakes let us
drive them (and the endpoints, via a patched ``get_db``) without a real DB.
"""
from __future__ import annotations

import os

os.environ.setdefault("OSINT_DB_URL", "postgresql+asyncpg://u:p@localhost/db")
os.environ.setdefault("OSINT_APIKEY_HASH_SECRET", "unit-test-secret")
os.environ.setdefault("OSINT_ENVIRONMENT", "development")

import pathlib  # noqa: E402
import sys  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))  # backend/

from typing import Any  # noqa: E402


class FakeRow:
    """A row that supports both attribute access (r.id) and ._mapping (dict(r._mapping))."""

    def __init__(self, d: dict[str, Any]) -> None:
        self.__dict__.update(d)
        self._mapping = dict(d)


def _wrap(x: Any) -> Any:
    return FakeRow(x) if isinstance(x, dict) else x


class FakeResult:
    def __init__(self, rows: Any) -> None:
        self._r = [_wrap(x) for x in (rows or [])]

    def fetchall(self):
        return self._r

    def fetchone(self):
        return self._r[0] if self._r else None

    def first(self):
        return self._r[0] if self._r else None

    def all(self):
        return self._r

    @property
    def rowcount(self) -> int:
        return len(self._r)


class _Begin:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *a):
        return False


class FakeSession:
    """Yields canned results in order — one per ``execute`` call.

    ``results`` is a list; each element is the row-list for the Nth execute().
    Past the end, execute() returns an empty result (so extra queries are safe).
    """

    def __init__(self, results: list[Any] | None = None) -> None:
        self._results = list(results or [])
        self._i = 0
        self.executed: list[tuple[str, dict | None]] = []

    async def execute(self, sql: Any, params: dict | None = None) -> FakeResult:
        rows = self._results[self._i] if self._i < len(self._results) else []
        self._i += 1
        try:
            self.executed.append((str(sql), params))
        except Exception:
            self.executed.append(("<sql>", params))
        return FakeResult(rows)

    async def commit(self) -> None:
        return None

    def begin(self) -> _Begin:
        return _Begin()


class _DBCtx:
    """Async context manager mirroring ``db.get_db()`` — ``async with get_db() as db``."""

    def __init__(self, session: FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> FakeSession:
        return self._session

    async def __aexit__(self, *a):
        return False


def fake_get_db_factory(*result_batches: list[Any]):
    """Return a ``get_db`` replacement.

    Each call to the returned ``get_db()`` yields a fresh FakeSession seeded from
    the next batch (endpoints may open several ``async with get_db()`` blocks per
    request). After the batches are exhausted, an empty session is yielded.
    """
    batches = list(result_batches)
    state = {"i": 0}

    def get_db() -> _DBCtx:
        idx = state["i"]
        state["i"] += 1
        seed = batches[idx] if idx < len(batches) else []
        return _DBCtx(FakeSession(seed))

    return get_db


def single_db(results: list[Any]):
    """A ``get_db`` where every ``get_db()`` call yields a session seeded with the
    SAME result list (handy when an endpoint opens one db block)."""
    def get_db() -> _DBCtx:
        return _DBCtx(FakeSession(list(results)))
    return get_db
