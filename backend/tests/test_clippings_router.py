"""
Tests for backend.routers.clippings_router.

Focus: the two new endpoints powering the Cuttings Newsstand redesign.
    GET  /api/clippings/papers      — newsstand mastheads
    GET  /api/newspapers/{id}/pdf   — on-demand PDF stream

Mirrors the FakeSession pattern from test_clips_router.py — no real DB.
"""
from __future__ import annotations

import base64
import json
import time
import types
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import clippings_router as clippings_module
from backend.routers.clippings_router import clippings_router, newspapers_router

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

    monkeypatch.setattr(clippings_module, "get_db", fake_get_db)


def make_app() -> FastAPI:
    """Mount the routers and bypass the page-access RBAC gate so the unit
    tests can exercise endpoint logic without seeding the page-access
    tables. JWT auth on `get_current_user` is left intact so the
    requires-auth tests still meaningfully exercise that path."""
    from backend.auth.auth_middleware import get_current_principal

    async def _fake_principal() -> dict:
        return {
            "user_id": TEST_USER_ID,
            "role": "super_admin",
            "is_impersonating": False,
            "impersonator_id": None,
        }

    app = FastAPI()
    app.dependency_overrides[get_current_principal] = _fake_principal
    app.include_router(clippings_router)
    app.include_router(newspapers_router)
    return app


def _paper_row(
    name: str = "Times of India",
    language: str = "en",
    clip_count: int = 5,
    pdf_available: bool = True,
    edition_date: date | None = None,
) -> FakeRow:
    return FakeRow(
        newspaper_id=str(uuid4()),
        name=name,
        language=language,
        edition_date=edition_date or date.today(),
        clip_count=clip_count,
        pdf_available=pdf_available,
    )


# ── /api/clippings/papers ────────────────────────────────────────────────────

@pytest.mark.unit
def test_papers_endpoint_requires_auth() -> None:
    client = TestClient(make_app())
    r = client.get("/api/clippings/papers")
    assert r.status_code == 401


@pytest.mark.unit
def test_papers_endpoint_returns_papers_sorted_by_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sess = FakeSession([
        [
            _paper_row("Times of India", "en", clip_count=12),
            _paper_row("The Hindu", "en", clip_count=7),
            _paper_row("Sakshi", "te", clip_count=3, pdf_available=False),
        ]
    ])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())

    r = client.get(
        "/api/clippings/papers",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["papers"]) == 3
    assert [p["name"] for p in data["papers"]] == [
        "Times of India", "The Hindu", "Sakshi",
    ]
    assert [p["clip_count"] for p in data["papers"]] == [12, 7, 3]
    assert data["papers"][2]["pdf_available"] is False


@pytest.mark.unit
def test_papers_endpoint_empty_when_no_clippings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_db(monkeypatch, FakeSession([[]]))
    client = TestClient(make_app())
    r = client.get(
        "/api/clippings/papers",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    assert r.json() == {"papers": []}


@pytest.mark.unit
def test_papers_endpoint_filters_by_relevance_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The SQL must include the >= 0.3 relevance filter so noise is excluded."""
    sess = FakeSession([[]])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    client.get(
        "/api/clippings/papers",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    query, _ = sess.calls[0]
    assert "relevance_score >= 0.3" in query


@pytest.mark.unit
def test_papers_endpoint_includes_zero_clip_papers_with_pdf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A paper with 0 clippings but a resolvable PDF edition must still surface."""
    sess = FakeSession([
        [
            _paper_row("Times of India", "en", clip_count=12, pdf_available=True),
            _paper_row("Dainik Bhaskar", "hi", clip_count=0, pdf_available=True),
        ]
    ])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())

    r = client.get(
        "/api/clippings/papers",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    names = [p["name"] for p in r.json()["papers"]]
    assert "Dainik Bhaskar" in names
    # The query must allow paper to pass via clip_count > 0 OR pdf_available.
    query, _ = sess.calls[0]
    assert "HAVING" in query
    assert "BOOL_OR(ne.pdf_url IS NOT NULL)" in query


@pytest.mark.unit
def test_papers_endpoint_respects_days_param(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sess = FakeSession([[]])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    client.get(
        "/api/clippings/papers?days=14",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    _, params = sess.calls[0]
    assert params["days"] == 14


@pytest.mark.unit
def test_papers_endpoint_rejects_days_out_of_bounds() -> None:
    client = TestClient(make_app())
    r = client.get(
        "/api/clippings/papers?days=0",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 422
    r = client.get(
        "/api/clippings/papers?days=999",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 422


# ── /api/newspapers/{id}/pdf ─────────────────────────────────────────────────

@pytest.mark.unit
def test_pdf_endpoint_requires_auth() -> None:
    client = TestClient(make_app())
    nid = str(uuid4())
    r = client.get(f"/api/newspapers/{nid}/pdf")
    assert r.status_code == 401


@pytest.mark.unit
def test_pdf_endpoint_404_when_no_url_resolvable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No cached row, no careerswave URL → 404."""
    nid = str(uuid4())
    sess = FakeSession([
        [],  # cache lookup: no row
        [],  # source lookup: no row
    ])
    install_fake_db(monkeypatch, sess)

    async def fake_resolve(_url: str) -> str | None:
        return None
    monkeypatch.setattr(
        clippings_module, "get_pdf_url_from_careerswave", fake_resolve,
    )

    client = TestClient(make_app())
    r = client.get(
        f"/api/newspapers/{nid}/pdf",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 404


@pytest.mark.unit
def test_pdf_endpoint_serves_cached_url_when_fresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh cache row → re-fetch is skipped, careerswave is NOT hit."""
    nid = str(uuid4())
    cached_url = "https://drive.google.com/uc?export=download&id=CACHED"
    sess = FakeSession([
        [FakeRow(pdf_url=cached_url, fetched_at=datetime.now(timezone.utc))],
    ])
    install_fake_db(monkeypatch, sess)

    careerswave_called = {"count": 0}

    async def fake_resolve(_url: str) -> str | None:
        careerswave_called["count"] += 1
        return None
    monkeypatch.setattr(
        clippings_module, "get_pdf_url_from_careerswave", fake_resolve,
    )

    captured: dict[str, str] = {}

    class _StubResp:
        status_code = 200
        async def aiter_bytes(self, chunk_size: int = 65536):
            yield b"%PDF-1.4 stub\n"

    class _StubStream:
        def __init__(self, _client, _method, url):
            captured["url"] = url
        async def __aenter__(self):
            return _StubResp()
        async def __aexit__(self, *a):
            return None

    class _StubClient:
        def __init__(self, *a, **kw): pass
        def stream(self, method, url):
            return _StubStream(self, method, url)
        async def aclose(self): return None

    monkeypatch.setattr(clippings_module.httpx, "AsyncClient", _StubClient)

    client = TestClient(make_app())
    r = client.get(
        f"/api/newspapers/{nid}/pdf",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert b"%PDF" in r.content
    assert captured["url"] == cached_url
    assert careerswave_called["count"] == 0


@pytest.mark.unit
def test_pdf_endpoint_refetches_when_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cache row older than 6h → re-resolve via careerswave + upsert."""
    nid = str(uuid4())
    stale = datetime.now(timezone.utc) - timedelta(hours=12)
    sess = FakeSession([
        [FakeRow(pdf_url="https://stale", fetched_at=stale)],   # cache hit (stale)
        [FakeRow(careerswave_url="https://www.careerswave.in/foo/")],  # source row
        [],  # upsert
    ])
    install_fake_db(monkeypatch, sess)

    fresh_url = "https://drive.google.com/uc?export=download&id=FRESH"

    async def fake_resolve(_url: str) -> str | None:
        return fresh_url
    monkeypatch.setattr(
        clippings_module, "get_pdf_url_from_careerswave", fake_resolve,
    )

    captured: dict[str, str] = {}

    class _StubResp:
        status_code = 200
        async def aiter_bytes(self, chunk_size: int = 65536):
            yield b"%PDF-1.4 fresh\n"

    class _StubStream:
        def __init__(self, _c, _m, url):
            captured["url"] = url
        async def __aenter__(self): return _StubResp()
        async def __aexit__(self, *a): return None

    class _StubClient:
        def __init__(self, *a, **kw): pass
        def stream(self, method, url): return _StubStream(self, method, url)
        async def aclose(self): return None

    monkeypatch.setattr(clippings_module.httpx, "AsyncClient", _StubClient)

    client = TestClient(make_app())
    r = client.get(
        f"/api/newspapers/{nid}/pdf",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    assert captured["url"] == fresh_url
    upsert_query, _ = sess.calls[2]
    assert "INSERT INTO newspaper_editions" in upsert_query


@pytest.mark.unit
def test_pdf_endpoint_rejects_bad_date_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_db(monkeypatch, FakeSession([]))
    client = TestClient(make_app())
    nid = str(uuid4())
    r = client.get(
        f"/api/newspapers/{nid}/pdf?date=not-a-date",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 400


# ── /api/clippings/feed ──────────────────────────────────────────────────────


def _clipping_row(
    *,
    newspaper_name: str = "Times of India",
    newspaper_language: str = "en",
    headline: str = "Test headline",
    relevance_score: float = 0.6,
    has_image: bool = True,
    collected_at: datetime | None = None,
    edition_date: date | None = None,
) -> FakeRow:
    return FakeRow(
        clipping_id=str(uuid4()),
        newspaper_name=newspaper_name,
        newspaper_language=newspaper_language,
        edition_date=edition_date or date.today(),
        page_number=1,
        headline=headline,
        headline_translated=None,
        text_preview="preview text " * 5,
        translated_preview=None,
        has_image=has_image,
        relevance_score=relevance_score,
        relevance_explanation="Mentioned",
        collected_at=collected_at or datetime.now(timezone.utc),
    )


@pytest.mark.unit
def test_feed_endpoint_requires_auth() -> None:
    client = TestClient(make_app())
    r = client.get("/api/clippings/feed")
    assert r.status_code == 401


@pytest.mark.unit
def test_feed_endpoint_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Feed returns clippings + the masthead summary."""
    sess = FakeSession([
        # First .execute() — main feed query
        [
            _clipping_row(headline="A", relevance_score=0.9),
            _clipping_row(headline="B", relevance_score=0.5),
        ],
        # Second .execute() — newspapers summary
        [
            FakeRow(newspaper_name="Times of India", newspaper_language="en", count=10),
        ],
    ])
    install_fake_db(monkeypatch, sess)

    client = TestClient(make_app())
    r = client.get(
        "/api/clippings/feed?limit=20",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["clippings"]) == 2
    assert body["clippings"][0]["headline"] == "A"
    assert body["has_more"] is False
    assert body["next_cursor"] is None
    assert body["newspapers"][0]["name"] == "Times of India"


@pytest.mark.unit
def test_feed_applies_relevance_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """The feed query must include the >= 0.3 relevance gate."""
    sess = FakeSession([[], []])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    client.get(
        "/api/clippings/feed",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    main_query, _ = sess.calls[0]
    assert "relevance_score >= 0.3" in main_query


@pytest.mark.unit
def test_feed_applies_newspaper_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = FakeSession([[], []])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    client.get(
        "/api/clippings/feed?newspaper=Sakshi",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    main_query, params = sess.calls[0]
    assert "nc.newspaper_name = :paper" in main_query
    assert params["paper"] == "Sakshi"


@pytest.mark.unit
def test_feed_applies_language_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = FakeSession([[], []])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    client.get(
        "/api/clippings/feed?language=te",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    main_query, params = sess.calls[0]
    assert "nc.newspaper_language = :lang" in main_query
    assert params["lang"] == "te"


@pytest.mark.unit
def test_feed_pagination_cursor_emitted_when_has_more(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the SQL returned limit+1 rows, the response must signal has_more
    and emit a cursor anchored on the last visible row's collected_at."""
    cutoff = datetime(2026, 4, 28, 6, 0, tzinfo=timezone.utc)
    rows = [
        _clipping_row(
            collected_at=cutoff - timedelta(minutes=i),
            relevance_score=0.7 - i * 0.001,
        )
        for i in range(3)
    ]
    sess = FakeSession([rows, []])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    r = client.get(
        "/api/clippings/feed?limit=2",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["clippings"]) == 2
    assert body["has_more"] is True
    assert body["next_cursor"] is not None


@pytest.mark.unit
def test_feed_cursor_param_threads_into_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sess = FakeSession([[], []])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    cursor = "2026-04-28T05:00:00Z"  # Z form survives URL parsing without encoding
    client.get(
        f"/api/clippings/feed?cursor={cursor}",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    main_query, params = sess.calls[0]
    assert "nc.collected_at < :cursor::timestamptz" in main_query
    assert params["cursor"] == cursor


@pytest.mark.unit
def test_feed_rejects_limit_out_of_bounds() -> None:
    client = TestClient(make_app())
    r = client.get(
        "/api/clippings/feed?limit=0",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 422
    r = client.get(
        "/api/clippings/feed?limit=999",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 422


@pytest.mark.unit
def test_feed_papers_summary_respects_days_param(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defect B2: the inner papers summary used a hardcoded 7-day window
    and silently ignored the user-supplied ?days param. After the fix the
    query must thread :days through. This test pins the corrected behavior."""
    sess = FakeSession([[], []])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    client.get(
        "/api/clippings/feed?days=14",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    papers_query, papers_params = sess.calls[1]
    assert "INTERVAL '7 days'" not in papers_query, (
        "papers subquery must not hardcode 7 days"
    )
    assert ":days" in papers_query
    assert papers_params["days"] == 14


# ── /api/clippings/{id}/image ────────────────────────────────────────────────


@pytest.mark.unit
def test_image_endpoint_requires_auth() -> None:
    client = TestClient(make_app())
    r = client.get(f"/api/clippings/{uuid4()}/image")
    assert r.status_code == 401


@pytest.mark.unit
def test_image_endpoint_returns_b64(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = FakeSession([[FakeRow(clipping_image_b64="iVBORw0KGgoFAKEPNG")]])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    r = client.get(
        f"/api/clippings/{uuid4()}/image",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    assert r.json() == {"image_b64": "iVBORw0KGgoFAKEPNG"}


@pytest.mark.unit
def test_image_endpoint_404_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = FakeSession([[]])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    r = client.get(
        f"/api/clippings/{uuid4()}/image",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 404


# ── /api/clippings/{id}/full ─────────────────────────────────────────────────


@pytest.mark.unit
def test_full_endpoint_requires_auth() -> None:
    client = TestClient(make_app())
    r = client.get(f"/api/clippings/{uuid4()}/full")
    assert r.status_code == 401


@pytest.mark.unit
def test_full_endpoint_returns_both_languages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cid = uuid4()
    sess = FakeSession([
        [FakeRow(
            id=cid,
            headline="తెలుగు headline",
            headline_translated="Translated headline",
            article_text="తెలుగు body",
            article_text_translated="Translated body",
            newspaper_name="Sakshi",
            edition_date=date(2026, 4, 28),
        )]
    ])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    r = client.get(
        f"/api/clippings/{cid}/full",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["headline"] == "తెలుగు headline"
    assert body["headline_translated"] == "Translated headline"
    assert body["article_text"] == "తెలుగు body"
    assert body["article_text_translated"] == "Translated body"
    assert body["newspaper_name"] == "Sakshi"
    assert body["edition_date"] == "2026-04-28"


@pytest.mark.unit
def test_full_endpoint_404_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = FakeSession([[]])
    install_fake_db(monkeypatch, sess)
    client = TestClient(make_app())
    r = client.get(
        f"/api/clippings/{uuid4()}/full",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 404
