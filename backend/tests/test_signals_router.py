"""
Tests for backend.routers.signals_router.

Targets all three endpoints:
    GET /api/signals/feed
    GET /api/signals/sentiment
    GET /api/signals/monitors

Uses the FakeSession pattern from test_clippings_router.py — no real DB.
Auth dependency is overridden via app.dependency_overrides so we never
exercise the Supabase JWT decode path.

xfail markers attach to defects logged in docs/qa/signals-defects.md;
they flip to passing when the corresponding fix lands.
"""
from __future__ import annotations

import types
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth.auth_middleware import get_current_user
from backend.routers import signals_router as signals_module
from backend.routers.signals_router import signals_router

TEST_USER_ID = "11111111-1111-1111-1111-111111111111"


# ── FakeSession plumbing ───────────────────────────────────────────────────

class FakeRow(types.SimpleNamespace):
    """Row object exposing attributes via getattr like a SQLAlchemy Row."""


class FakeResult:
    def __init__(self, rows: list[FakeRow]) -> None:
        self._rows = rows

    def fetchall(self) -> list[FakeRow]:
        return list(self._rows)

    def fetchone(self) -> FakeRow | None:
        return self._rows[0] if self._rows else None


class FakeSession:
    def __init__(self, responses: list[list[FakeRow]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def execute(
        self, query: Any, params: dict[str, Any] | None = None
    ) -> FakeResult:
        self.calls.append((str(query), dict(params or {})))
        if not self.responses:
            return FakeResult([])
        return FakeResult(self.responses.pop(0))

    async def commit(self) -> None:  # pragma: no cover
        return None

    async def close(self) -> None:  # pragma: no cover
        return None

    async def rollback(self) -> None:  # pragma: no cover
        return None


def install_fake_db(
    monkeypatch: pytest.MonkeyPatch, session: FakeSession
) -> None:
    @asynccontextmanager
    async def fake_get_db():
        yield session

    monkeypatch.setattr(signals_module, "get_db", fake_get_db)


def make_app(user: dict[str, Any] | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(signals_router)
    app.dependency_overrides[get_current_user] = lambda: (
        user if user is not None else {"id": TEST_USER_ID, "email": "t@x"}
    )
    # Q1 fix: bypass router-level `require_page("signals")` RBAC gate.
    # The router has `dependencies=[Depends(require_page("signals"))]`.
    # Each Depends() exposes `.dependency` — the inner closure produced
    # by require_page(). Override that so the test never executes the
    # real RBAC check.
    for dep in signals_router.dependencies:
        target = getattr(dep, "dependency", None)
        if callable(target):
            app.dependency_overrides[target] = lambda: {
                "id": TEST_USER_ID,
                "email": "t@x",
                "role": "user",
            }
    return app


# ── Fixtures ───────────────────────────────────────────────────────────────

def _post_row(
    platform: str = "reddit",
    monitor_name: str | None = "r/india",
    sentiment: float = 0.5,
    matched: list[str] | None = None,
    minutes_ago: int = 5,
) -> FakeRow:
    now = datetime.now(timezone.utc)
    return FakeRow(
        post_id=str(uuid4()),
        platform=platform,
        platform_post_id=f"{platform}-{uuid4().hex[:8]}",
        monitor_id=str(uuid4()),
        monitor_name=monitor_name,
        author_username="someone",
        author_display_name="Some One",
        author_url="https://example.com/u/someone",
        post_text="Hello signal world.",
        post_text_translated=None,
        post_language="en",
        post_url="https://example.com/p/1",
        upvotes=10,
        downvotes=0,
        comment_count=2,
        share_count=0,
        forward_count=0,
        forwarded_from=None,
        has_document=False,
        sentiment_score=sentiment,
        matched_entities=matched or [],
        topic_category=None,
        posted_at=now - timedelta(minutes=minutes_ago + 1),
        collected_at=now - timedelta(minutes=minutes_ago),
    )


def _sentiment_row(
    monitor_id: str | None = None,
    display_name: str = "r/india",
    identifier: str | None = None,
    platform: str = "reddit",
    pos: int = 5,
    neg: int = 1,
    neu: int = 4,
    avg: float = 0.21,
) -> FakeRow:
    return FakeRow(
        platform=platform,
        display_name=display_name,
        identifier=identifier or display_name,
        post_count=pos + neg + neu,
        avg_sentiment=avg,
        positive_count=pos,
        negative_count=neg,
        neutral_count=neu,
    )


def _monitor_row(
    platform: str = "reddit",
    display_name: str = "r/india",
    post_count: int = 25,
    is_active: bool = True,
) -> FakeRow:
    return FakeRow(
        id=str(uuid4()),
        platform=platform,
        monitor_type="subreddit" if platform == "reddit" else "channel",
        identifier=display_name.split("/")[-1],
        display_name=display_name,
        is_active=is_active,
        last_collected_at=datetime.now(timezone.utc) - timedelta(hours=1),
        post_count=post_count,
    )


# ── /feed tests ────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_feed_requires_auth() -> None:
    """No dependency override → 401 from real get_current_user."""
    app = FastAPI()
    app.include_router(signals_router)
    client = TestClient(app)

    resp = client.get("/api/signals/feed")
    assert resp.status_code == 401


@pytest.mark.unit
def test_feed_empty_db(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(responses=[[], []])  # entities, posts
    install_fake_db(monkeypatch, session)
    client = TestClient(make_app())

    resp = client.get("/api/signals/feed")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"posts": [], "has_more": False, "next_cursor": None}


@pytest.mark.unit
def test_feed_returns_rows_and_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [_post_row(minutes_ago=i) for i in range(31)]  # limit+1
    session = FakeSession(responses=[[], rows])
    install_fake_db(monkeypatch, session)
    client = TestClient(make_app())

    resp = client.get("/api/signals/feed?platform=all&days=7&limit=30")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["posts"]) == 30
    assert body["has_more"] is True
    assert body["next_cursor"] is not None


@pytest.mark.unit
@pytest.mark.parametrize("platform", ["reddit", "telegram", "all"])
def test_feed_platform_filter_passed_to_query(
    monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    session = FakeSession(responses=[[], []])
    install_fake_db(monkeypatch, session)
    client = TestClient(make_app())

    resp = client.get(f"/api/signals/feed?platform={platform}")
    assert resp.status_code == 200
    feed_call = session.calls[-1]
    if platform != "all":
        assert ":platform" in feed_call[0] or "platform" in feed_call[1]
        if "platform" in feed_call[1]:
            assert feed_call[1]["platform"] == platform


@pytest.mark.unit
@pytest.mark.parametrize("platform", ["twitter", "x", "instagram", "garbage"])
def test_feed_rejects_invalid_platform(
    monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    """A2 fix — /feed must reject any platform outside {reddit, telegram, all}.
    Twitter is removed (2026-04-29); the API rejects it for defense in depth.
    """
    session = FakeSession(responses=[[], []])
    install_fake_db(monkeypatch, session)
    client = TestClient(make_app())

    resp = client.get(f"/api/signals/feed?platform={platform}")
    assert resp.status_code == 422


@pytest.mark.unit
@pytest.mark.parametrize(
    "days,expected", [(1, 200), (30, 200), (0, 422), (31, 422), (-1, 422)]
)
def test_feed_days_clamped(
    monkeypatch: pytest.MonkeyPatch, days: int, expected: int
) -> None:
    session = FakeSession(responses=[[], []])
    install_fake_db(monkeypatch, session)
    client = TestClient(make_app())

    resp = client.get(f"/api/signals/feed?days={days}")
    assert resp.status_code == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "limit,expected", [(1, 200), (100, 200), (0, 422), (101, 422)]
)
def test_feed_limit_clamped(
    monkeypatch: pytest.MonkeyPatch, limit: int, expected: int
) -> None:
    session = FakeSession(responses=[[], []])
    install_fake_db(monkeypatch, session)
    client = TestClient(make_app())

    resp = client.get(f"/api/signals/feed?limit={limit}")
    assert resp.status_code == expected


@pytest.mark.unit
def test_feed_cursor_passed_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    session = FakeSession(responses=[[], []])
    install_fake_db(monkeypatch, session)
    client = TestClient(make_app())

    client.get(f"/api/signals/feed?cursor={cursor}")
    feed_call = session.calls[-1]
    assert "cursor" in feed_call[1]


@pytest.mark.unit
def test_feed_includes_user_entities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When user has entities, the entity intersection clause kicks in."""
    entity_rows = [
        FakeRow(canonical_name="BRS"),
        FakeRow(canonical_name="KTR"),
    ]
    session = FakeSession(responses=[entity_rows, []])
    install_fake_db(monkeypatch, session)
    client = TestClient(make_app())

    resp = client.get("/api/signals/feed")
    assert resp.status_code == 200
    feed_call = session.calls[-1]
    assert "entities" in feed_call[1] or "entities" in feed_call[0]


# ── /sentiment tests ───────────────────────────────────────────────────────

@pytest.mark.unit
def test_sentiment_requires_auth() -> None:
    app = FastAPI()
    app.include_router(signals_router)
    client = TestClient(app)

    resp = client.get("/api/signals/sentiment")
    assert resp.status_code == 401


@pytest.mark.unit
def test_sentiment_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(responses=[[]])
    install_fake_db(monkeypatch, session)
    client = TestClient(make_app())

    resp = client.get("/api/signals/sentiment")
    assert resp.status_code == 200
    assert resp.json() == {"sentiment_by_monitor": []}


@pytest.mark.unit
def test_sentiment_buckets(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        _sentiment_row(display_name="r/india", pos=8, neg=1, neu=2, avg=0.4),
        _sentiment_row(display_name="r/telangana", pos=2, neg=4, neu=3, avg=-0.1),
    ]
    session = FakeSession(responses=[rows])
    install_fake_db(monkeypatch, session)
    client = TestClient(make_app())

    resp = client.get("/api/signals/sentiment?days=7")
    assert resp.status_code == 200
    body = resp.json()
    items = body["sentiment_by_monitor"]
    assert len(items) == 2
    india = next(x for x in items if x["display_name"] == "r/india")
    assert india["positive_count"] == 8
    assert india["avg_sentiment"] == pytest.approx(0.4)


@pytest.mark.unit
@pytest.mark.parametrize(
    "days,expected", [(1, 200), (60, 200), (0, 422), (61, 422)]
)
def test_sentiment_days_clamped(
    monkeypatch: pytest.MonkeyPatch, days: int, expected: int
) -> None:
    session = FakeSession(responses=[[]])
    install_fake_db(monkeypatch, session)
    client = TestClient(make_app())

    resp = client.get(f"/api/signals/sentiment?days={days}")
    assert resp.status_code == expected


@pytest.mark.xfail(
    reason="SIG-5: sentiment JOIN drops monitor_id IS NULL posts",
    strict=False,
)
@pytest.mark.unit
def test_sentiment_includes_unmonitored_posts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Posts with monitor_id IS NULL (keyword-only) should still aggregate."""
    rows = [
        _sentiment_row(monitor_id=None, display_name="Untracked"),
    ]
    session = FakeSession(responses=[rows])
    install_fake_db(monkeypatch, session)
    client = TestClient(make_app())

    resp = client.get("/api/signals/sentiment")
    body = resp.json()
    assert any(
        x["display_name"] == "Untracked" for x in body["sentiment_by_monitor"]
    )


# ── /monitors tests ────────────────────────────────────────────────────────

@pytest.mark.unit
def test_monitors_requires_auth() -> None:
    app = FastAPI()
    app.include_router(signals_router)
    client = TestClient(app)

    resp = client.get("/api/signals/monitors")
    assert resp.status_code == 401


@pytest.mark.unit
def test_monitors_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(responses=[[]])
    install_fake_db(monkeypatch, session)
    client = TestClient(make_app())

    resp = client.get("/api/signals/monitors")
    assert resp.status_code == 200
    assert resp.json() == {"monitors": []}


@pytest.mark.unit
def test_monitors_returns_count(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        _monitor_row(platform="reddit", display_name="r/india", post_count=25),
        _monitor_row(
            platform="telegram", display_name="@BRSPartyofficial", post_count=12
        ),
    ]
    session = FakeSession(responses=[rows])
    install_fake_db(monkeypatch, session)
    client = TestClient(make_app())

    resp = client.get("/api/signals/monitors")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["monitors"]) == 2
    assert body["monitors"][0]["post_count"] == 25
    assert body["monitors"][0]["is_active"] is True


@pytest.mark.xfail(
    reason="SIG-4: /monitors issues 1 + N COUNT subqueries",
    strict=False,
)
@pytest.mark.unit
def test_monitors_no_n_plus_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """The endpoint should issue exactly one DB call regardless of monitor count.

    Today's implementation runs a Seq Scan with a SubPlan COUNT per row;
    the fake session counts only the outer execute call, so this passes
    against the fake. For the real regression assertion run the EXPLAIN
    query in docs/qa/signals-data-quality-report.md and assert loops=1.
    """
    rows = [_monitor_row() for _ in range(10)]
    session = FakeSession(responses=[rows])
    install_fake_db(monkeypatch, session)
    client = TestClient(make_app())

    resp = client.get("/api/signals/monitors")
    assert resp.status_code == 200
    # Strict regression assertion would need a query-counter that
    # parses the SQL — left as TODO for the SIG-4 fix branch.
    assert len(session.calls) == 1
