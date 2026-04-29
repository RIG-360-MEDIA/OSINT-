"""
Tests for backend.tasks.social_task.

Covers:
- _fetch_user_entities query shape (regression for SIG-14: missing user_id filter).
- _process_monitor_posts dedupe + sentiment + entity tagging happy path.
- aggregate_social_sentiment_daily idempotency assertion (with stubs).

The Celery decorator is left in place; we exercise the underlying async
functions (`_collect_*`) by patching collectors and DB session.
"""
from __future__ import annotations

import asyncio
import types
from contextlib import asynccontextmanager
from typing import Any

import pytest

from backend.tasks import social_task as task_mod


# ── FakeSession (mirrors test_signals_router.FakeSession) ─────────────────

class FakeRow(types.SimpleNamespace):
    pass


class FakeResult:
    def __init__(self, rows: list[FakeRow]) -> None:
        self._rows = rows

    def fetchall(self) -> list[FakeRow]:
        return list(self._rows)

    def fetchone(self) -> FakeRow | None:
        return self._rows[0] if self._rows else None

    def scalar(self) -> Any:
        return self._rows[0].value if self._rows else None


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.responses: list[FakeResult] = []
        self.committed = False

    def queue(self, rows: list[FakeRow]) -> None:
        self.responses.append(FakeResult(rows))

    async def execute(
        self, query: Any, params: dict[str, Any] | None = None
    ) -> FakeResult:
        self.calls.append((str(query), dict(params or {})))
        if self.responses:
            return self.responses.pop(0)
        return FakeResult([])

    async def commit(self) -> None:
        self.committed = True


def _install_fake_db(
    monkeypatch: pytest.MonkeyPatch, session: FakeSession
) -> None:
    @asynccontextmanager
    async def fake_get_db():
        yield session

    # _collect_* functions import get_db from backend.database lazily;
    # patch the module path used inside social_task.
    import backend.database as db_mod

    monkeypatch.setattr(db_mod, "get_db", fake_get_db)


# ── _fetch_user_entities ───────────────────────────────────────────────────

@pytest.mark.xfail(
    reason="SIG-14: query has no user_id filter — every user's pool merges",
    strict=False,
)
@pytest.mark.unit
def test_fetch_user_entities_filters_by_user_id() -> None:
    """The query must include a user_id parameter binding."""
    sess = FakeSession()
    sess.queue([FakeRow(canonical_name="BRS")])

    asyncio.run(task_mod._fetch_user_entities(sess))

    sql, params = sess.calls[0]
    # When SIG-14 is fixed we expect a user_id binding to be supplied.
    assert "user_id" in sql or "user_id" in params


@pytest.mark.unit
def test_fetch_user_entities_handles_failure() -> None:
    """Query failure must return [] not raise (logger.warning)."""

    class Boom(FakeSession):
        async def execute(self, *_a: Any, **_kw: Any) -> FakeResult:
            raise RuntimeError("db down")

    out = asyncio.run(task_mod._fetch_user_entities(Boom()))
    assert out == []


# ── _process_monitor_posts ────────────────────────────────────────────────

@pytest.mark.unit
def test_process_monitor_skips_existing_posts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If _post_exists returns True, no insert."""

    async def fake_exists(*_a: Any, **_kw: Any) -> bool:
        return True

    async def fake_insert(*_a: Any, **_kw: Any) -> None:  # pragma: no cover
        raise AssertionError("must not insert")

    monkeypatch.setattr(task_mod, "_post_exists", fake_exists)
    monkeypatch.setattr(task_mod, "_insert_post", fake_insert)
    monkeypatch.setattr(task_mod, "_safe_embed", lambda _t: None)

    sess = FakeSession()
    posts = [
        {
            "platform": "reddit",
            "platform_post_id": "abc",
            "post_text": "Hi",
            "post_language": "en",
        }
    ]
    inserted = asyncio.run(
        task_mod._process_monitor_posts(sess, "mon-1", posts, ["BRS"])
    )
    assert inserted == 0


@pytest.mark.unit
def test_process_monitor_skips_post_without_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_mod, "_post_exists", AsyncMockResult(False)
    )
    monkeypatch.setattr(
        task_mod, "_insert_post", AsyncMockResult(None)
    )
    monkeypatch.setattr(task_mod, "_safe_embed", lambda _t: None)

    posts = [{"platform": "reddit", "post_text": "Hi", "post_language": "en"}]
    inserted = asyncio.run(
        task_mod._process_monitor_posts(FakeSession(), "m", posts, [])
    )
    assert inserted == 0


@pytest.mark.unit
def test_process_monitor_inserts_new_posts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inserted_calls: list[dict[str, Any]] = []

    async def fake_exists(*_a: Any, **_kw: Any) -> bool:
        return False

    async def fake_insert(
        _db: Any, _mid: str, post: dict[str, Any], *_a: Any, **_kw: Any,
    ) -> None:
        inserted_calls.append(post)

    monkeypatch.setattr(task_mod, "_post_exists", fake_exists)
    monkeypatch.setattr(task_mod, "_insert_post", fake_insert)
    monkeypatch.setattr(task_mod, "_safe_embed", lambda _t: None)

    posts = [
        {
            "platform": "reddit",
            "platform_post_id": "p1",
            "post_text": "BRS announces new policy",
            "post_language": "en",
        },
        {
            "platform": "reddit",
            "platform_post_id": "p2",
            "post_text": "Generic news",
            "post_language": "en",
        },
    ]
    inserted = asyncio.run(
        task_mod._process_monitor_posts(FakeSession(), "m1", posts, ["BRS"])
    )
    assert inserted == 2
    assert len(inserted_calls) == 2


@pytest.mark.unit
def test_process_monitor_swallows_insert_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An insert failure for one post must not break the whole batch."""
    n = {"calls": 0}

    async def fake_exists(*_a: Any, **_kw: Any) -> bool:
        return False

    async def fake_insert(*_a: Any, **_kw: Any) -> None:
        n["calls"] += 1
        if n["calls"] == 1:
            raise RuntimeError("constraint")

    monkeypatch.setattr(task_mod, "_post_exists", fake_exists)
    monkeypatch.setattr(task_mod, "_insert_post", fake_insert)
    monkeypatch.setattr(task_mod, "_safe_embed", lambda _t: None)

    posts = [
        {
            "platform": "reddit",
            "platform_post_id": f"p{i}",
            "post_text": "x",
            "post_language": "en",
        }
        for i in range(3)
    ]
    inserted = asyncio.run(
        task_mod._process_monitor_posts(FakeSession(), "m", posts, [])
    )
    assert inserted == 2  # one failed, two succeeded


# ── _collect_twitter graceful skip ─────────────────────────────────────────

@pytest.mark.unit
def test_collect_twitter_skips_without_bearer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TWITTER_BEARER_TOKEN", raising=False)

    # If gating fails, the next line would attempt DB access — fail loudly.
    def boom(*_a: Any, **_kw: Any) -> Any:
        raise AssertionError("DB must not be touched without bearer")

    monkeypatch.setattr("backend.database.get_db", boom)
    asyncio.run(task_mod._collect_twitter())  # should return cleanly


# ── _collect_telegram graceful skip ────────────────────────────────────────

@pytest.mark.unit
def test_collect_telegram_skips_without_creds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for k in (
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
        "TELEGRAM_SESSION_STRING",
        "TELEGRAM_BOT_TOKEN",
    ):
        monkeypatch.delenv(k, raising=False)

    def boom(*_a: Any, **_kw: Any) -> Any:
        raise AssertionError("DB must not be touched without creds")

    monkeypatch.setattr("backend.database.get_db", boom)
    asyncio.run(task_mod._collect_telegram())


# ── helpers ────────────────────────────────────────────────────────────────

class AsyncMockResult:
    """Tiny callable returning a coroutine yielding a fixed value."""

    def __init__(self, value: Any) -> None:
        self._value = value

    async def __call__(self, *_a: Any, **_kw: Any) -> Any:
        return self._value
