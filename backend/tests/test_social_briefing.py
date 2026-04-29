"""
Tests for the Signal Room briefing pipeline.

Covers:
  - /api/signals/briefing      (router smoke + shape)
  - /api/signals/timeline      (shape + Twitter exclusion)
  - /api/signals/cluster/{id}/posts  (drilldown shape + filter)
  - _greedy_cosine_cluster pure-function correctness
  - _summarise_cluster headline + summary derivation

Mirrors the FakeSession pattern from test_signals_router.py.
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
from backend.tasks.social_briefing_task import (
    _greedy_cosine_cluster,
    _summarise_cluster,
)

TEST_USER_ID = "11111111-1111-1111-1111-111111111111"


# ── FakeSession plumbing (mirror of test_signals_router) ──────────────────

class FakeRow(types.SimpleNamespace):
    pass


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


def install_fake_db(
    monkeypatch: pytest.MonkeyPatch, session: FakeSession
) -> None:
    @asynccontextmanager
    async def fake_get_db():
        yield session

    monkeypatch.setattr(signals_module, "get_db", fake_get_db)


def make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(signals_router)
    app.dependency_overrides[get_current_user] = lambda: {
        "id": TEST_USER_ID,
        "email": "t@x",
    }
    return app


def _cluster_row(
    headline: str = "Sample headline",
    post_count: int = 5,
    platforms: list[str] | None = None,
    tone: str = "neutral",
) -> FakeRow:
    now = datetime.now(timezone.utc)
    return FakeRow(
        id=str(uuid4()),
        window_start=now - timedelta(hours=24),
        window_end=now,
        headline=headline,
        summary=headline + " — a summary",
        post_count=post_count,
        platforms=platforms or ["reddit", "telegram"],
        monitor_names=["r/india", "MIB_India"],
        top_entities=["BRS", "Telangana"],
        avg_sentiment=0.0 if tone == "neutral" else 0.4 if tone == "positive" else -0.4,
        sentiment_tone=tone,
        representative_post_ids=[uuid4(), uuid4()],
        sample_languages=["en", "te"],
        created_at=now,
    )


def _timeline_row(hour_offset: int, posts: int = 4) -> FakeRow:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return FakeRow(
        bucket=now - timedelta(hours=hour_offset),
        platform="reddit",
        posts=posts,
        avg_sentiment=0.1,
        positive=2,
        negative=1,
    )


def _drill_post_row(platform: str = "reddit", text: str = "Hello") -> FakeRow:
    now = datetime.now(timezone.utc)
    return FakeRow(
        post_id=str(uuid4()),
        platform=platform,
        author_username="someone",
        post_text=text,
        post_text_translated=None,
        post_language="en",
        post_url="https://x.example/p/1",
        upvotes=3,
        comment_count=1,
        share_count=0,
        forward_count=0,
        forwarded_from=None,
        has_document=False,
        sentiment_score=0.2,
        matched_entities=["BRS"],
        posted_at=now - timedelta(minutes=10),
        collected_at=now - timedelta(minutes=5),
        monitor_name="r/india",
    )


# ── /briefing ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_briefing_requires_auth() -> None:
    app = FastAPI()
    app.include_router(signals_router)
    client = TestClient(app)
    assert client.get("/api/signals/briefing").status_code == 401


@pytest.mark.unit
def test_briefing_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession(responses=[[]]))
    client = TestClient(make_app())
    r = client.get("/api/signals/briefing")
    assert r.status_code == 200
    body = r.json()
    assert body == {"as_of": None, "clusters": []}


@pytest.mark.unit
def test_briefing_returns_clusters(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        _cluster_row("Story A", post_count=10, tone="positive"),
        _cluster_row("Story B", post_count=4, tone="negative"),
    ]
    install_fake_db(monkeypatch, FakeSession(responses=[rows]))
    client = TestClient(make_app())
    body = client.get("/api/signals/briefing").json()
    assert len(body["clusters"]) == 2
    assert body["clusters"][0]["headline"] == "Story A"
    assert body["clusters"][0]["post_count"] == 10
    assert body["clusters"][0]["sentiment_tone"] == "positive"
    assert body["as_of"] is not None


@pytest.mark.unit
def test_briefing_filters_twitter_from_platforms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Twitter is hidden from the user UI; briefing must scrub it."""
    rows = [
        _cluster_row(
            "Mixed", platforms=["reddit", "twitter", "telegram"]
        ),
    ]
    install_fake_db(monkeypatch, FakeSession(responses=[rows]))
    client = TestClient(make_app())
    body = client.get("/api/signals/briefing").json()
    assert "twitter" not in body["clusters"][0]["platforms"]
    assert set(body["clusters"][0]["platforms"]) == {"reddit", "telegram"}


@pytest.mark.unit
@pytest.mark.parametrize(
    "limit,expected",
    [(1, 200), (30, 200), (0, 422), (31, 422)],
)
def test_briefing_limit_clamped(
    monkeypatch: pytest.MonkeyPatch, limit: int, expected: int
) -> None:
    install_fake_db(monkeypatch, FakeSession(responses=[[]]))
    client = TestClient(make_app())
    assert (
        client.get(f"/api/signals/briefing?limit={limit}").status_code
        == expected
    )


# ── /timeline ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_timeline_requires_auth() -> None:
    app = FastAPI()
    app.include_router(signals_router)
    client = TestClient(app)
    assert client.get("/api/signals/timeline").status_code == 401


@pytest.mark.unit
def test_timeline_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession(responses=[[]]))
    client = TestClient(make_app())
    r = client.get("/api/signals/timeline")
    assert r.status_code == 200
    assert r.json() == {"buckets": []}


@pytest.mark.unit
def test_timeline_aggregates(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [_timeline_row(i, posts=i + 1) for i in range(5)]
    install_fake_db(monkeypatch, FakeSession(responses=[rows]))
    client = TestClient(make_app())
    body = client.get("/api/signals/timeline?hours=12").json()
    assert len(body["buckets"]) == 5
    assert body["buckets"][0]["platform"] == "reddit"
    assert body["buckets"][0]["posts"] >= 1


@pytest.mark.unit
@pytest.mark.parametrize(
    "hours,expected",
    [(1, 200), (72, 200), (0, 422), (73, 422)],
)
def test_timeline_hours_clamped(
    monkeypatch: pytest.MonkeyPatch, hours: int, expected: int
) -> None:
    install_fake_db(monkeypatch, FakeSession(responses=[[]]))
    client = TestClient(make_app())
    assert (
        client.get(f"/api/signals/timeline?hours={hours}").status_code
        == expected
    )


# ── /cluster/{id}/posts (drilldown) ───────────────────────────────────────


@pytest.mark.unit
def test_drilldown_requires_auth() -> None:
    app = FastAPI()
    app.include_router(signals_router)
    client = TestClient(app)
    cid = str(uuid4())
    assert (
        client.get(f"/api/signals/cluster/{cid}/posts").status_code == 401
    )


@pytest.mark.unit
def test_drilldown_returns_posts(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        _drill_post_row(platform="reddit", text="reddit post"),
        _drill_post_row(platform="telegram", text="telegram post"),
    ]
    install_fake_db(monkeypatch, FakeSession(responses=[rows]))
    client = TestClient(make_app())
    body = client.get(f"/api/signals/cluster/{uuid4()}/posts").json()
    assert len(body["posts"]) == 2
    assert {p["post_text"] for p in body["posts"]} == {
        "reddit post",
        "telegram post",
    }


@pytest.mark.unit
def test_drilldown_filters_twitter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        _drill_post_row(platform="reddit", text="keep me"),
        _drill_post_row(platform="twitter", text="drop me"),
    ]
    install_fake_db(monkeypatch, FakeSession(responses=[rows]))
    client = TestClient(make_app())
    body = client.get(f"/api/signals/cluster/{uuid4()}/posts").json()
    texts = {p["post_text"] for p in body["posts"]}
    assert "keep me" in texts
    assert "drop me" not in texts


# ── Pure-function tests for the clustering helpers ─────────────────────────


def _post(post_id: str, emb: list[float], **kwargs: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": post_id,
        "platform": "reddit",
        "body": "text",
        "language": "en",
        "sentiment": 0.0,
        "entities": [],
        "upvotes": 1,
        "comments": 0,
        "collected_at": datetime.now(timezone.utc),
        "monitor_name": "r/india",
        "emb": emb,
    }
    base.update(kwargs)
    return base


@pytest.mark.unit
def test_greedy_cluster_groups_similar_embeddings() -> None:
    near_a = [1.0, 0.0, 0.0, 0.0]
    near_a2 = [0.99, 0.01, 0.0, 0.0]
    near_b = [0.0, 1.0, 0.0, 0.0]
    near_b2 = [0.0, 0.99, 0.01, 0.0]
    posts = [
        _post("a1", near_a),
        _post("b1", near_b),
        _post("a2", near_a2),
        _post("b2", near_b2),
    ]
    out = _greedy_cosine_cluster(posts)
    # Two clusters expected (a1+a2, b1+b2).
    assert len(out) == 2
    sizes = sorted(len(c["post_ids"]) for c in out)
    assert sizes == [2, 2]


@pytest.mark.unit
def test_greedy_cluster_drops_singletons() -> None:
    """Posts with no near neighbours are noise and must not be clusters."""
    posts = [
        _post("a", [1.0, 0.0, 0.0]),
        _post("b", [0.0, 1.0, 0.0]),
        _post("c", [0.0, 0.0, 1.0]),
    ]
    out = _greedy_cosine_cluster(posts)
    assert out == []


@pytest.mark.unit
def test_greedy_cluster_handles_empty_input() -> None:
    assert _greedy_cosine_cluster([]) == []


@pytest.mark.unit
def test_summarise_cluster_picks_engagement_leader() -> None:
    members = [
        _post(
            "lo", [1, 0, 0],
            body="boring filler",
            upvotes=1,
            comments=0,
        ),
        _post(
            "hi", [1, 0, 0],
            body="The big story everyone is talking about. Details follow.",
            upvotes=50,
            comments=10,
        ),
    ]
    headline, summary = _summarise_cluster(members)
    assert "big story" in headline.lower()
    assert "2 posts" in summary


@pytest.mark.unit
def test_summarise_cluster_empty_returns_empty_strings() -> None:
    assert _summarise_cluster([]) == ("", "")
