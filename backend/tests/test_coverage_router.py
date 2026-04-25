"""
Tests for backend.routers.coverage_router.

Covers four endpoints: GET /feed, GET /search, POST /summary/{id},
GET /article/{id}.

Strategy: mount only coverage_router on a fresh FastAPI app, override
auth via dependency_overrides, and monkeypatch get_db to yield a
FakeSession that replays scripted rows. No real DB or Groq calls.

Run from project root:
    pytest backend/tests/test_coverage_router.py -v
"""
from __future__ import annotations

import base64
import json
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth.auth_middleware import get_current_user
from backend.routers import coverage_router as cov_module
from backend.routers.coverage_router import coverage_router

# ── Helpers ──────────────────────────────────────────────────────────────────

TEST_USER_ID = "11111111-1111-1111-1111-111111111111"


def make_jwt(
    sub: str = TEST_USER_ID,
    email: str = "test@example.com",
    exp_offset: int = 3600,
) -> str:
    """Construct an unsigned-but-decodable JWT for the auth middleware."""
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


@dataclass
class FakeRow:
    """Row object exposing attributes via getattr like SQLAlchemy Row."""
    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class FakeResult:
    def __init__(self, rows: list[FakeRow]) -> None:
        self._rows = rows

    def fetchall(self) -> list[FakeRow]:
        return list(self._rows)

    def fetchone(self) -> FakeRow | None:
        return self._rows[0] if self._rows else None


class FakeSession:
    """
    Stand-in async session.

    Each call to .execute() pops the next scripted result off `responses`.
    All issued queries are recorded in `.calls` for assertion.
    """

    def __init__(self, responses: list[list[FakeRow]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, query: Any, params: dict | None = None) -> FakeResult:
        self.calls.append((str(query), dict(params or {})))
        if not self.responses:
            return FakeResult([])
        return FakeResult(self.responses.pop(0))

    async def close(self) -> None:  # noqa: D401
        return None

    async def rollback(self) -> None:
        return None


def install_fake_db(monkeypatch: pytest.MonkeyPatch, session: FakeSession) -> None:
    """Patch the get_db symbol used inside coverage_router."""
    @asynccontextmanager
    async def fake_get_db():
        yield session

    monkeypatch.setattr(cov_module, "get_db", fake_get_db)


def make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(coverage_router)
    return app


def _article_row(**overrides: Any) -> FakeRow:
    """Default feed/article row matching the SELECT in coverage_router."""
    aid = overrides.pop("article_id", str(uuid4()))
    base: dict[str, Any] = {
        "article_id": aid,
        "title": "Sample headline",
        "url": "https://example.com/a",
        "thumbnail_url": None,
        "author_name": None,
        "topic_category": "POLITICS",
        "geo_primary": "IN",
        "published_at": None,
        "collected_at": None,
        "language_detected": "en",
        "text_length": 250,
        "source_name": "Example Wire",
        "source_domain": "example.com",
        "score_final": 0.75,
        "score_stage1": 0.5,
        "relevance_tier": 1,
        "relevance_explanation": "matched X",
        "matched_entity_names": ["X"],
        "geo_multiplier_applied": 1.0,
        "sentiment_for_user": "NEUTRAL",
        "scored_at": None,
    }
    base.update(overrides)
    return FakeRow(**base)


def _totals_row() -> FakeRow:
    return FakeRow(total=10, tier1=3, tier2=4, tier3=3)


# ── Auth tests ────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_feed_requires_auth_header(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([]))
    client = TestClient(make_app())
    r = client.get("/api/coverage/feed")
    assert r.status_code in (401, 403)  # FastAPI HTTPBearer returns 403 by default


@pytest.mark.unit
def test_feed_rejects_malformed_token(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([]))
    client = TestClient(make_app())
    r = client.get(
        "/api/coverage/feed",
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert r.status_code == 401
    assert "Malformed" in r.json()["detail"]


@pytest.mark.unit
def test_feed_rejects_expired_token(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([]))
    client = TestClient(make_app())
    expired = make_jwt(exp_offset=-3600)
    r = client.get(
        "/api/coverage/feed",
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert r.status_code == 401
    assert "expired" in r.json()["detail"].lower()


# ── Feed: filter parsing ──────────────────────────────────────────────────────

@pytest.mark.unit
def test_feed_default_tiers_are_1_2_3(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default tier query should bind tiers=[1,2,3] to the SQL."""
    sess = FakeSession([[_article_row()], [_totals_row()]])
    install_fake_db(monkeypatch, sess)

    client = TestClient(make_app())
    r = client.get(
        "/api/coverage/feed",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    feed_query, feed_params = sess.calls[0]
    assert feed_params["tiers"] == [1, 2, 3]
    assert feed_params["user_id"] == TEST_USER_ID


@pytest.mark.unit
def test_feed_topic_uppercased(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = FakeSession([[_article_row()], [_totals_row()]])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    r = client.get(
        "/api/coverage/feed?topic=politics,economics",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    _, params = sess.calls[0]
    assert params["topics"] == ["POLITICS", "ECONOMICS"]


@pytest.mark.unit
def test_feed_sentiment_filter_applied_only_when_not_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """sentiment=all must NOT add a sentiment param/condition."""
    sess = FakeSession([[_article_row()], [_totals_row()]])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    client.get(
        "/api/coverage/feed?sentiment=all",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    feed_query, feed_params = sess.calls[0]
    assert "sentiment" not in feed_params
    # WHERE clause must NOT bind a sentiment param. The SELECT lists
    # uar.sentiment_for_user as a column, so we check the WHERE side.
    where_part = feed_query.split("WHERE", 1)[1].split("ORDER BY", 1)[0]
    assert "sentiment_for_user" not in where_part

    sess2 = FakeSession([[_article_row()], [_totals_row()]])
    install_fake_db(monkeypatch, sess2)
    client.get(
        "/api/coverage/feed?sentiment=FOR_USER",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    _, params2 = sess2.calls[0]
    assert params2["sentiment"] == "FOR_USER"


@pytest.mark.unit
def test_feed_sort_relevance_vs_recency_orders_differ(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sess_rel = FakeSession([[_article_row()], [_totals_row()]])
    install_fake_db(monkeypatch, sess_rel)
    client = TestClient(make_app())
    client.get(
        "/api/coverage/feed?sort=relevance",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    rel_query, _ = sess_rel.calls[0]
    assert "score_final DESC" in rel_query

    sess_rec = FakeSession([[_article_row()], [_totals_row()]])
    install_fake_db(monkeypatch, sess_rec)
    client.get(
        "/api/coverage/feed?sort=recency",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    rec_query, _ = sess_rec.calls[0]
    assert "collected_at DESC" in rec_query
    assert "score_final DESC" not in rec_query


# ── Feed: pagination & cursor robustness ──────────────────────────────────────

@pytest.mark.unit
def test_feed_garbage_cursor_does_not_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed cursor must be silently ignored — try/except in router."""
    for bad in ["garbage", "no_underscore", "abc_", "_abc", "x_y_z"]:
        sess = FakeSession([[_article_row()], [_totals_row()]])
        install_fake_db(monkeypatch, sess)
        client = TestClient(make_app())
        r = client.get(
            f"/api/coverage/feed?cursor={bad}",
            headers={"Authorization": f"Bearer {make_jwt()}"},
        )
        assert r.status_code == 200, f"cursor {bad!r} crashed"


@pytest.mark.unit
def test_feed_has_more_when_more_than_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Feed asks for limit+1 internally and trims; has_more is set when extra row present."""
    rows = [_article_row(article_id=str(uuid4())) for _ in range(21)]
    sess = FakeSession([rows, [_totals_row()]])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    r = client.get(
        "/api/coverage/feed?limit=20",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    body = r.json()
    assert body["pagination"]["has_more"] is True
    assert body["pagination"]["next_cursor"] is not None
    assert len(body["articles"]) == 20  # trimmed
    # cursor format: "{score:.6f}_{article_id}"
    assert "_" in body["pagination"]["next_cursor"]


@pytest.mark.unit
def test_feed_no_has_more_when_under_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sess = FakeSession([[_article_row()], [_totals_row()]])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    r = client.get(
        "/api/coverage/feed?limit=20",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    body = r.json()
    assert body["pagination"]["has_more"] is False
    assert body["pagination"]["next_cursor"] is None


@pytest.mark.unit
def test_feed_limit_validator_clamps_above_50(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Query validator: limit has le=50 — 100 → 422."""
    install_fake_db(monkeypatch, FakeSession([]))
    client = TestClient(make_app())
    r = client.get(
        "/api/coverage/feed?limit=100",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 422


@pytest.mark.unit
def test_feed_totals_in_response(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = FakeSession([[_article_row()], [_totals_row()]])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    body = client.get(
        "/api/coverage/feed",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    ).json()
    assert body["totals"] == {"total": 10, "tier1": 3, "tier2": 4, "tier3": 3}


# ── Search ────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_search_min_length_2_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([]))
    client = TestClient(make_app())
    r = client.get(
        "/api/coverage/search?q=a",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 422  # Query(..., min_length=2)


@pytest.mark.unit
def test_search_uses_parameterised_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SQL injection probe — q is bound, never interpolated. The dangerous
    string should arrive verbatim in params, not in the query text."""
    sess = FakeSession([[]])  # zero hits
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    evil = "'; DROP TABLE users;--"
    r = client.get(
        "/api/coverage/search",
        params={"q": evil},
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    sql, params = sess.calls[0]
    assert params["query"] == evil
    assert params["like_query"] == f"%{evil}%"
    assert "DROP TABLE" not in sql


@pytest.mark.unit
def test_search_zero_results(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = FakeSession([[]])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    body = client.get(
        "/api/coverage/search?q=quantum",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    ).json()
    assert body == {"query": "quantum", "count": 0, "articles": []}


@pytest.mark.unit
def test_search_default_tiers_when_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty tier param should fall back to [1,2,3]."""
    sess = FakeSession([[]])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    client.get(
        "/api/coverage/search?q=test&tier=",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    _, params = sess.calls[0]
    assert params["tiers"] == [1, 2, 3]


# ── Summary ───────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_summary_404_when_article_not_in_user_feed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sess = FakeSession([[]])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    r = client.post(
        f"/api/coverage/summary/{uuid4()}",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 404


@pytest.mark.unit
def test_summary_short_text_fallback_skips_groq(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Body < 50 chars must return the canned message and NOT invoke Groq."""
    short_row = FakeRow(
        title="t",
        lead_text_translated="too short",
        lead_text_original=None,
        topic_category="POLITICS",
        geo_primary="IN",
        relevance_explanation="x",
    )
    sess = FakeSession([[short_row]])
    install_fake_db(monkeypatch, sess)

    groq_called = {"n": 0}

    async def boom(*_a: Any, **_kw: Any) -> str:
        groq_called["n"] += 1
        raise AssertionError("Groq must not be called for short text")

    monkeypatch.setattr(cov_module, "call_groq", boom)

    client = TestClient(make_app())
    r = client.post(
        f"/api/coverage/summary/{uuid4()}",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "unavailable" in body["summary"].lower()
    assert body["cached"] is False
    assert groq_called["n"] == 0


@pytest.mark.unit
def test_summary_success_path_calls_groq(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    long_text = "Lorem ipsum dolor sit amet, " * 20
    row = FakeRow(
        title="Big news",
        lead_text_translated=long_text,
        lead_text_original=None,
        topic_category="POLITICS",
        geo_primary="IN",
        relevance_explanation="x",
    )
    sess = FakeSession([[row]])
    install_fake_db(monkeypatch, sess)

    captured: dict[str, Any] = {}

    async def fake_groq(system: str, user: str, **kw: Any) -> str:
        captured.update(system=system, user=user, **kw)
        return "Three sentence summary. About something. Important."

    monkeypatch.setattr(cov_module, "call_groq", fake_groq)

    client = TestClient(make_app())
    r = client.post(
        f"/api/coverage/summary/{uuid4()}",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    assert r.json()["summary"].startswith("Three sentence summary")
    assert captured["task_type"] == "brief_generation"
    # Body was truncated to 1500 chars upstream
    assert len(captured["user"]) <= 1500 + len("Title: Big news\n\n")


@pytest.mark.unit
def test_summary_groq_failure_returns_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    long_text = "x" * 200
    row = FakeRow(
        title="t",
        lead_text_translated=long_text,
        lead_text_original=None,
        topic_category="POLITICS",
        geo_primary="IN",
        relevance_explanation="x",
    )
    sess = FakeSession([[row]])
    install_fake_db(monkeypatch, sess)

    async def fail(*_a: Any, **_kw: Any) -> str:
        raise RuntimeError("groq down")

    monkeypatch.setattr(cov_module, "call_groq", fail)

    client = TestClient(make_app())
    r = client.post(
        f"/api/coverage/summary/{uuid4()}",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 500
    assert "Summary generation failed" in r.json()["detail"]


# ── Single article ────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_article_404_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = FakeSession([[]])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    r = client.get(
        f"/api/coverage/article/{uuid4()}",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 404


@pytest.mark.unit
def test_article_success_returns_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sess = FakeSession([[_article_row()]])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    r = client.get(
        f"/api/coverage/article/{uuid4()}",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert {
        "article_id", "title", "url", "source_name", "score_final",
        "relevance_tier", "matched_entity_names", "sentiment_for_user",
    }.issubset(body.keys())
    assert body["sentiment_for_user"] == "NEUTRAL"
