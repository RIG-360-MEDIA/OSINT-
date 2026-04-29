"""
Tests for backend.routers.clips_router (The Clip Room).

Covers three endpoints:
    GET  /api/clips/feed
    GET  /api/clips/channels
    POST /api/clips/channels

Strategy: mount only clips_router on a fresh FastAPI app, override auth via
dependency_overrides where useful, and monkeypatch get_db to yield a
FakeSession that replays scripted rows. No real DB calls.

Run from project root:
    pytest backend/tests/test_clips_router.py -v
"""
from __future__ import annotations

import base64
import json
import time
import types
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import clips_router as clips_module
from backend.routers.clips_router import clips_router

# ── Helpers ──────────────────────────────────────────────────────────────────

TEST_USER_ID = "11111111-1111-1111-1111-111111111111"


def make_jwt(
    sub: str = TEST_USER_ID,
    email: str = "test@example.com",
    exp_offset: int = 3600,
) -> str:
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps({
            "sub": sub,
            "email": email,
            "exp": int(time.time()) + exp_offset,
        }).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.fake_signature"


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
    """Stand-in async session replaying scripted results in order."""

    def __init__(self, responses: list[list[FakeRow]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, query: Any, params: dict | None = None) -> FakeResult:
        self.calls.append((str(query), dict(params or {})))
        if not self.responses:
            return FakeResult([])
        return FakeResult(self.responses.pop(0))

    async def commit(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


def install_fake_db(monkeypatch: pytest.MonkeyPatch, session: FakeSession) -> None:
    @asynccontextmanager
    async def fake_get_db():
        yield session

    monkeypatch.setattr(clips_module, "get_db", fake_get_db)


def make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(clips_router)
    # The router-level `require_page("clips")` runs its own DB lookup against
    # `user_page_access` (via auth_middleware.get_db, which we do NOT patch).
    # Without this override, every authenticated request reaches the real DB
    # and fails with socket.gaierror outside the docker network.
    for dep in clips_router.dependencies:
        app.dependency_overrides[dep.dependency] = lambda: None
    return app


def _entity_row(name: str = "Modi") -> FakeRow:
    return FakeRow(canonical_name=name)


def _clip_row(**overrides: Any) -> FakeRow:
    """Default ranked-clip row matching the SELECT in clips_router."""
    base: dict[str, Any] = {
        "clip_id": str(uuid4()),
        "video_id": "abc123",
        "video_title": "Test broadcast",
        "channel_id": "UC" + "X" * 22,
        "channel_name": "Test Channel",
        "video_published_at": datetime.now(timezone.utc),
        "video_url": "https://youtube.com/watch?v=abc123",
        "clip_start_seconds": 60,
        "clip_end_seconds": 90,
        "embed_url": "https://www.youtube.com/embed/abc123?start=60&end=90",
        "transcript_segment": "Modi spoke about reforms during the address.",
        "transcript_language": "hi",
        "transcript_translated": "Modi spoke about reforms during the address.",
        "matched_entity": "Modi",
        "all_entities": ["Modi"],
        "relevance_score": 0.8,
        "has_transcript": True,
        "collected_at": datetime.now(timezone.utc),
    }
    base.update(overrides)
    return FakeRow(**base)


def _channel_row(channel_id: str = "UC" + "X" * 22, name: str = "Test Channel", count: int = 3) -> FakeRow:
    return FakeRow(channel_id=channel_id, channel_name=name, clip_count=count)


def _total_row(total: int = 5) -> FakeRow:
    return FakeRow(total=total)


# ── Auth gate ────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_feed_requires_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([]))
    client = TestClient(make_app())
    r = client.get("/api/clips/feed")
    assert r.status_code in (401, 403)


@pytest.mark.unit
def test_feed_rejects_malformed_token(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([]))
    client = TestClient(make_app())
    r = client.get(
        "/api/clips/feed",
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert r.status_code == 401


@pytest.mark.unit
def test_feed_rejects_expired_token(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([]))
    client = TestClient(make_app())
    r = client.get(
        "/api/clips/feed",
        headers={"Authorization": f"Bearer {make_jwt(exp_offset=-3600)}"},
    )
    assert r.status_code == 401


# ── Empty user_entities short-circuit ────────────────────────────────────────

@pytest.mark.unit
def test_feed_empty_user_entities_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = FakeSession([[]])  # entities query returns no rows
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    r = client.get(
        "/api/clips/feed",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "clips": [], "has_more": False, "next_cursor": None,
        "total": 0, "channels": [], "user_entities": [],
    }
    # Only the entities query should have run
    assert len(sess.calls) == 1


# ── Happy path ────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_feed_happy_path_renders_clips(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = FakeSession([
        [_entity_row("Modi")],            # user_entities
        [_clip_row(), _clip_row()],       # ranked feed
        [_total_row(2)],                  # total count
        [_channel_row()],                 # channel breakdown
    ])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    r = client.get(
        "/api/clips/feed",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["clips"]) == 2
    assert body["total"] == 2
    assert body["user_entities"] == ["Modi"]
    assert body["channels"][0]["channel_name"] == "Test Channel"
    assert body["has_more"] is False
    assert body["next_cursor"] is None
    # Clip shape
    clip = body["clips"][0]
    for key in (
        "clip_id", "video_id", "video_title", "channel_name", "channel_id",
        "video_url", "embed_url", "clip_start_seconds", "clip_end_seconds",
        "transcript_segment", "transcript_translated", "matched_entity",
        "transcript_language", "video_published_at", "collected_at",
    ):
        assert key in clip


# ── Filter parameters ────────────────────────────────────────────────────────

@pytest.mark.unit
def test_feed_entity_filter_binds_param(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = FakeSession([
        [_entity_row("Modi")],
        [_clip_row()],
        [_total_row(1)],
        [_channel_row()],
    ])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    client.get(
        "/api/clips/feed?entity=Modi",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    # Second call is the ranked-feed query
    feed_query, feed_params = sess.calls[1]
    assert feed_params["entity"] == "Modi"
    assert "yc.matched_entity = :entity" in feed_query


@pytest.mark.unit
def test_feed_channel_filter_binds_param(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = FakeSession([
        [_entity_row("Modi")],
        [_clip_row()],
        [_total_row(1)],
        [_channel_row()],
    ])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    client.get(
        "/api/clips/feed?channel=UCXXX",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    feed_query, feed_params = sess.calls[1]
    assert feed_params["channel"] == "UCXXX"
    assert "yc.channel_id = :channel" in feed_query


@pytest.mark.unit
def test_feed_total_reflects_active_filters_after_fix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B1 fix: total query must accept entity/channel filters into its params."""
    sess = FakeSession([
        [_entity_row("Modi"), _entity_row("Adani")],
        [_clip_row()],
        [_total_row(7)],
        [_channel_row()],
    ])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    r = client.get(
        "/api/clips/feed?entity=Modi&channel=UC1",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    # Third call is the count(*) query — after fix it should bind the filters.
    total_query, total_params = sess.calls[2]
    assert "matched_entity = :entity" in total_query
    assert total_params.get("entity") == "Modi"
    assert "channel_id = :channel" in total_query
    assert total_params.get("channel") == "UC1"


@pytest.mark.unit
def test_feed_channels_aggregation_respects_entity_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B2 fix: channels breakdown must respect entity filter."""
    sess = FakeSession([
        [_entity_row("Modi"), _entity_row("Adani")],
        [_clip_row()],
        [_total_row(1)],
        [_channel_row()],
    ])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    client.get(
        "/api/clips/feed?entity=Modi",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    ch_query, ch_params = sess.calls[3]
    assert "matched_entity = :entity" in ch_query
    assert ch_params.get("entity") == "Modi"


# ── Cursor pagination ────────────────────────────────────────────────────────

@pytest.mark.unit
def test_feed_has_more_when_extra_row(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [_clip_row() for _ in range(21)]
    sess = FakeSession([
        [_entity_row("Modi")],
        rows,
        [_total_row(21)],
        [_channel_row()],
    ])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    r = client.get(
        "/api/clips/feed?limit=20",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    body = r.json()
    assert body["has_more"] is True
    assert body["next_cursor"] is not None
    assert len(body["clips"]) == 20


@pytest.mark.unit
def test_feed_garbage_cursor_returns_400(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cursor validation: malformed input should return 400, not 500."""
    sess = FakeSession([[_entity_row("Modi")]])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    r = client.get(
        "/api/clips/feed",
        params={"cursor": "not-a-timestamp"},
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 400
    assert "ISO-8601" in r.json()["detail"]


@pytest.mark.unit
def test_feed_cursor_param_is_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = FakeSession([
        [_entity_row("Modi")],
        [_clip_row()],
        [_total_row(1)],
        [_channel_row()],
    ])
    install_fake_db(monkeypatch, sess)
    cursor_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    cursor = cursor_dt.isoformat()
    client = TestClient(make_app())
    client.get(
        "/api/clips/feed",
        params={"cursor": cursor},
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    feed_query, feed_params = sess.calls[1]
    assert "collected_at < :cursor_time" in feed_query
    assert feed_params["cursor_time"] == cursor_dt


# ── Bounds validation ────────────────────────────────────────────────────────

@pytest.mark.unit
def test_feed_limit_above_50_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([]))
    client = TestClient(make_app())
    r = client.get(
        "/api/clips/feed?limit=51",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 422


@pytest.mark.unit
def test_feed_limit_zero_or_negative_rejected_after_fix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B5 fix: limit must enforce ge=1."""
    install_fake_db(monkeypatch, FakeSession([]))
    client = TestClient(make_app())
    for bad in (0, -1):
        r = client.get(
            f"/api/clips/feed?limit={bad}",
            headers={"Authorization": f"Bearer {make_jwt()}"},
        )
        assert r.status_code == 422, f"limit={bad} should be rejected"


@pytest.mark.unit
def test_feed_days_out_of_range_rejected_after_fix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B6 fix: days must enforce ge=1, le=90."""
    install_fake_db(monkeypatch, FakeSession([]))
    client = TestClient(make_app())
    for bad in (0, -5, 999):
        r = client.get(
            f"/api/clips/feed?days={bad}",
            headers={"Authorization": f"Bearer {make_jwt()}"},
        )
        assert r.status_code == 422, f"days={bad} should be rejected"


# ── Channels endpoint ────────────────────────────────────────────────────────

@pytest.mark.unit
def test_list_channels_returns_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    row = FakeRow(
        channel_id="UC" + "X" * 22,
        channel_name="Test Channel",
        channel_url="https://youtube.com/channel/UCXXX",
        is_active=True,
        last_checked_at=datetime.now(timezone.utc),
        total_clips=42,
    )
    sess = FakeSession([[row]])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    r = client.get(
        "/api/clips/channels",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["channels"][0]["total_clips"] == 42
    assert body["channels"][0]["is_active"] is True


@pytest.mark.unit
def test_list_channels_requires_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([]))
    client = TestClient(make_app())
    r = client.get("/api/clips/channels")
    assert r.status_code in (401, 403)


# ── Add-channel endpoint ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_add_channel_via_body_after_fix(monkeypatch: pytest.MonkeyPatch) -> None:
    """B4 fix: POST /channels accepts JSON body, not query params."""
    sess = FakeSession([[]])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    r = client.post(
        "/api/clips/channels",
        json={
            "channel_id": "UC" + "X" * 22,
            "channel_name": "Test Channel",
        },
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    assert r.json()["success"] is True
    # Bound channel_id should appear in INSERT params
    _, insert_params = sess.calls[0]
    assert insert_params["cid"] == "UC" + "X" * 22


@pytest.mark.unit
def test_add_channel_rejects_invalid_channel_id_after_fix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B10 fix: channel_id must match ^UC[A-Za-z0-9_-]{22}$."""
    install_fake_db(monkeypatch, FakeSession([]))
    client = TestClient(make_app())
    r = client.post(
        "/api/clips/channels",
        json={"channel_id": "not-a-channel", "channel_name": "x"},
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 422


@pytest.mark.unit
def test_add_channel_requires_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([]))
    client = TestClient(make_app())
    r = client.post(
        "/api/clips/channels",
        json={"channel_id": "UC" + "X" * 22, "channel_name": "x"},
    )
    assert r.status_code in (401, 403)


# ── SQL injection probe ──────────────────────────────────────────────────────

@pytest.mark.unit
def test_feed_entity_param_is_bound_not_interpolated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SQL injection probe — entity must arrive in params verbatim."""
    sess = FakeSession([
        [_entity_row("Modi")],
        [],
        [_total_row(0)],
        [],
    ])
    install_fake_db(monkeypatch, sess)
    evil = "Modi'; DROP TABLE youtube_clips;--"
    client = TestClient(make_app())
    r = client.get(
        "/api/clips/feed",
        params={"entity": evil},
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    feed_query, feed_params = sess.calls[1]
    assert feed_params["entity"] == evil
    assert "DROP TABLE" not in feed_query
