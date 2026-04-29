"""
Tests for backend.routers.brief_router.

Mirrors the FakeSession pattern from test_clippings_router.py — no real DB,
no real Groq. The brief generator is monkeypatched to return a stub payload
so the router contract can be tested in isolation.

Endpoints under test:
    POST /api/brief/generate
    GET  /api/brief/today
    GET  /api/brief/{brief_date}
    GET  /api/brief/history/list
"""
from __future__ import annotations

import base64
import json
import time
import types
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import brief_router as brief_module
from backend.routers.brief_router import brief_router

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
    """Row exposing both attribute access and ._mapping like a SQLAlchemy Row."""

    @property
    def _mapping(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


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
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, query: Any, params: dict | None = None) -> FakeResult:
        self.calls.append((str(query), dict(params or {})))
        if not self.responses:
            return FakeResult([])
        return FakeResult(self.responses.pop(0))

    async def commit(self) -> None:
        return None


def install_fake_db(monkeypatch: pytest.MonkeyPatch, session: FakeSession) -> None:
    @asynccontextmanager
    async def fake_get_db():
        yield session

    monkeypatch.setattr(brief_module, "get_db", fake_get_db)


def make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(brief_router)
    return app


def _profile_row(**overrides: Any) -> FakeRow:
    base = dict(
        user_id=TEST_USER_ID,
        role_type="ANALYST",
        geo_primary="Telangana",
        geo_secondary="India",
        signal_priorities=["FINANCE", "POLITICS"],
        role_context="Senior data analyst, Hyderabad",
        raw_description="raw",
        language_preferences=["en"],
        brief_time="07:30",
        brief_timezone="Asia/Kolkata",
        organisation="RIG",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        entities=[],
    )
    base.update(overrides)
    return FakeRow(**base)


def _article_row(idx: int = 0, tier: int = 1) -> FakeRow:
    return FakeRow(
        id=str(uuid4()),
        title=f"Headline {idx}",
        lead_text_translated=f"Body {idx}",
        lead_text_original=f"Body {idx}",
        topic_category="POLITICS",
        geo_primary="Telangana",
        published_at=datetime.now(timezone.utc),
        thumbnail_url=None,
        author_name="Reporter",
        source_name="Test Source",
        domain="example.com",
        score_final=0.9 - idx * 0.01,
        relevance_tier=tier,
        relevance_explanation="explanation",
        matched_entity_names=[],
    )


def _brief_row(d: date | None = None, articles_used: int = 30) -> FakeRow:
    return FakeRow(
        content="# DAILY INTELLIGENCE BRIEF\n## body",
        brief_date=d or date.today(),
        articles_used=articles_used,
        generated_at=datetime.now(timezone.utc),
        model_used="llama-3.3-70b-versatile",
    )


# ── /api/brief/today ─────────────────────────────────────────────────────────

@pytest.mark.unit
def test_today_requires_auth() -> None:
    client = TestClient(make_app())
    r = client.get("/api/brief/today")
    assert r.status_code == 401


@pytest.mark.unit
def test_today_returns_404_when_no_brief(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([[]]))
    client = TestClient(make_app())
    r = client.get(
        "/api/brief/today",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 404
    assert "No brief for today" in r.json()["detail"]


@pytest.mark.unit
def test_today_returns_existing_brief(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = FakeSession([[_brief_row()]])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    r = client.get(
        "/api/brief/today",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "content" in body
    assert "brief_date" in body
    assert body["articles_used"] == 30


# ── /api/brief/{brief_date} ──────────────────────────────────────────────────

@pytest.mark.unit
def test_brief_by_date_rejects_invalid_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_db(monkeypatch, FakeSession([]))
    client = TestClient(make_app())
    r = client.get(
        "/api/brief/not-a-date",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 400


@pytest.mark.unit
def test_brief_by_date_404_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([[]]))
    client = TestClient(make_app())
    r = client.get(
        "/api/brief/2099-01-01",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 404


@pytest.mark.unit
def test_brief_by_date_returns_row(monkeypatch: pytest.MonkeyPatch) -> None:
    target = date(2026, 4, 20)
    install_fake_db(monkeypatch, FakeSession([[_brief_row(d=target, articles_used=12)]]))
    client = TestClient(make_app())
    r = client.get(
        f"/api/brief/{target.isoformat()}",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    assert r.json()["articles_used"] == 12
    assert r.json()["brief_date"] == "2026-04-20"


# ── /api/brief/history/list ──────────────────────────────────────────────────

@pytest.mark.unit
def test_history_caps_at_30(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = FakeSession([[_brief_row() for _ in range(30)]])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    r = client.get(
        "/api/brief/history/list",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    items = r.json()["briefs"]
    assert len(items) == 30
    query, _ = sess.calls[0]
    assert "LIMIT 30" in query


@pytest.mark.unit
def test_history_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([[]]))
    client = TestClient(make_app())
    r = client.get(
        "/api/brief/history/list",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    assert r.json() == {"briefs": []}


# ── /api/brief/generate ──────────────────────────────────────────────────────

@pytest.mark.unit
def test_generate_requires_auth() -> None:
    client = TestClient(make_app())
    r = client.post("/api/brief/generate")
    assert r.status_code == 401


@pytest.mark.unit
def test_generate_404_when_profile_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = FakeSession([
        [],  # ghost-row insert
        [],  # profile fetch — empty
    ])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    r = client.post(
        "/api/brief/generate",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 404
    assert "onboarding" in r.json()["detail"].lower()


@pytest.mark.unit
def test_generate_404_when_zero_articles(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = FakeSession([
        [],                  # ghost-row insert
        [_profile_row()],    # profile present
        [],                  # zero articles
    ])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    r = client.post(
        "/api/brief/generate",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 404
    assert "No relevant articles" in r.json()["detail"]


@pytest.mark.unit
def test_generate_425_when_below_minimum(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = FakeSession([
        [],
        [_profile_row()],
        [_article_row(i) for i in range(5)],   # only 5 — below 10-min threshold
    ])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    r = client.post(
        "/api/brief/generate",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 425
    assert "5 relevant articles" in r.json()["detail"]


@pytest.mark.unit
def test_generate_succeeds_with_enough_articles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sess = FakeSession([
        [],
        [_profile_row()],
        [_article_row(i) for i in range(15)],
        [],  # upsert
    ])
    install_fake_db(monkeypatch, sess)

    async def fake_generate_brief(**kwargs: Any) -> dict:
        return {
            "content": "# DAILY INTELLIGENCE BRIEF\n## body",
            "articles_used": kwargs["articles"].__len__(),
            "sections": {"SITUATION STATUS": "ok"},
        }

    monkeypatch.setattr(brief_module, "generate_brief", fake_generate_brief)

    client = TestClient(make_app())
    r = client.post(
        "/api/brief/generate",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["articles_used"] == 15
    assert body["content"].startswith("# DAILY INTELLIGENCE BRIEF")
    upsert_query, _ = sess.calls[3]
    assert "INSERT INTO briefs" in upsert_query
    assert "ON CONFLICT (user_id, brief_date) DO UPDATE" in upsert_query


@pytest.mark.unit
def test_generate_returns_500_when_generator_returns_no_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sess = FakeSession([
        [],
        [_profile_row()],
        [_article_row(i) for i in range(15)],
    ])
    install_fake_db(monkeypatch, sess)

    async def fake_generate_brief(**_: Any) -> dict:
        return {"content": None, "error": "groq_outage"}

    monkeypatch.setattr(brief_module, "generate_brief", fake_generate_brief)

    client = TestClient(make_app())
    r = client.post(
        "/api/brief/generate",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 500
    assert "groq_outage" in r.json()["detail"]


@pytest.mark.unit
def test_generate_filters_only_tier_1_and_2_in_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: SQL must filter by relevance_tier IN (1, 2) and exclude error articles."""
    sess = FakeSession([
        [],
        [_profile_row()],
        [_article_row(i) for i in range(15)],
        [],
    ])
    install_fake_db(monkeypatch, sess)

    async def fake_generate_brief(**_: Any) -> dict:
        return {"content": "ok", "articles_used": 15, "sections": {}}

    monkeypatch.setattr(brief_module, "generate_brief", fake_generate_brief)

    client = TestClient(make_app())
    client.post(
        "/api/brief/generate",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    article_query, _ = sess.calls[2]
    assert "relevance_tier IN (1, 2)" in article_query
    assert "nlp_confidence != 'error'" in article_query


# ── Defect-tracking tests (currently EXPECTED TO FAIL until fixed) ───────────

@pytest.mark.unit
@pytest.mark.xfail(
    reason="D-BRIEF-5: brief query lacks recency filter (a.published_at >= NOW() - INTERVAL).",
    strict=False,
)
def test_generate_query_has_recency_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = FakeSession([
        [], [_profile_row()], [_article_row(i) for i in range(15)], [],
    ])
    install_fake_db(monkeypatch, sess)

    async def fake_generate_brief(**_: Any) -> dict:
        return {"content": "ok", "articles_used": 15, "sections": {}}
    monkeypatch.setattr(brief_module, "generate_brief", fake_generate_brief)

    client = TestClient(make_app())
    client.post(
        "/api/brief/generate",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    article_query, _ = sess.calls[2]
    # Look for a WHERE-clause recency predicate, not just `published_at` in the
    # SELECT projection. The current query SELECTs published_at but never filters on it.
    assert "published_at >=" in article_query or "INTERVAL" in article_query, (
        "Recency filter missing — D-BRIEF-5"
    )


@pytest.mark.unit
@pytest.mark.xfail(
    reason="D-BRIEF-6: brief query does not exclude is_duplicate articles.",
    strict=False,
)
def test_generate_query_excludes_duplicates(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = FakeSession([
        [], [_profile_row()], [_article_row(i) for i in range(15)], [],
    ])
    install_fake_db(monkeypatch, sess)

    async def fake_generate_brief(**_: Any) -> dict:
        return {"content": "ok", "articles_used": 15, "sections": {}}
    monkeypatch.setattr(brief_module, "generate_brief", fake_generate_brief)

    client = TestClient(make_app())
    client.post(
        "/api/brief/generate",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    article_query, _ = sess.calls[2]
    assert "is_duplicate" in article_query, "Duplicate filter missing — D-BRIEF-6"
