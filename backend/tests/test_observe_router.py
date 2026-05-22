"""Smoke + auth tests for /api/observe/*.

Strategy: monkeypatch `require_super_admin` so we can hit the endpoints in a
unit-test context without needing a real cookie. Also patch the DB helpers
in `backend.observability.*` so we don't need a live Postgres.

Run inside the container:
  pytest backend/tests/test_observe_router.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth.auth_middleware import require_super_admin
from backend.routers.observe_router import observe_router


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def app_with_admin_override() -> FastAPI:
    """FastAPI app that auto-grants super_admin for the test caller."""
    app = FastAPI()
    app.include_router(observe_router)
    app.dependency_overrides[require_super_admin] = lambda: {"user_id": "test-admin",
                                                              "email": "admin@test"}
    return app


@pytest.fixture
def client(app_with_admin_override) -> TestClient:
    return TestClient(app_with_admin_override)


@pytest.fixture
def deny_app() -> FastAPI:
    """FastAPI app where require_super_admin raises 403."""
    from fastapi import HTTPException

    def _deny() -> None:
        raise HTTPException(status_code=403, detail="forbidden")
    app = FastAPI()
    app.include_router(observe_router)
    app.dependency_overrides[require_super_admin] = _deny
    return app


# ── Auth tests ───────────────────────────────────────────────────────────────

def test_endpoints_403_for_non_admin(deny_app: FastAPI) -> None:
    client = TestClient(deny_app)
    paths = [
        "/api/observe/ingest-pulse",
        "/api/observe/source-scorecard",
        "/api/observe/quality-monitor",
        "/api/observe/geo-heatmap",
        "/api/observe/story-pulse",
        "/api/observe/crosstab",
        "/api/observe/live-tail",
        "/api/observe/audit-queue",
    ]
    for p in paths:
        r = client.get(p)
        assert r.status_code == 403, f"{p} expected 403 got {r.status_code}"


# ── Smoke tests (DB mocked) ──────────────────────────────────────────────────

def _patch_db_helpers(returns: dict) -> list:
    """Return a list of patch objects for backend.observability.* helpers
    so each panel returns the supplied stub dict."""
    helpers = [
        ("backend.routers.observe_router.ingest_pulse", returns.get("ingest", {"by_hour": [], "per_source": [], "stalled_sources": [], "total_24h": 0})),
        ("backend.routers.observe_router.source_scorecard", returns.get("score", {"sources": []})),
        ("backend.routers.observe_router.quality_monitor", returns.get("quality", {"judge": None, "live": {}})),
        ("backend.routers.observe_router.geo_heatmap", returns.get("geo", {"level": "country", "regions": []})),
        ("backend.routers.observe_router.story_pulse", returns.get("story", {"clusters": []})),
        ("backend.routers.observe_router.crosstab", returns.get("crosstab", {"actor": None, "rows": []})),
        ("backend.routers.observe_router.live_tail", returns.get("tail", {"next_cursor": None, "articles": []})),
        ("backend.routers.observe_router.audit_queue", returns.get("queue", {"queue": []})),
    ]
    return [patch(name, AsyncMock(return_value=ret)) for name, ret in helpers]


def test_ingest_pulse_smoke(client: TestClient) -> None:
    patches = _patch_db_helpers({})
    for p in patches:
        p.start()
    try:
        r = client.get("/api/observe/ingest-pulse")
        assert r.status_code == 200
        body = r.json()
        assert "by_hour" in body and "per_source" in body and "stalled_sources" in body
    finally:
        for p in patches:
            p.stop()


def test_source_scorecard_smoke(client: TestClient) -> None:
    patches = _patch_db_helpers({})
    for p in patches:
        p.start()
    try:
        r = client.get("/api/observe/source-scorecard")
        assert r.status_code == 200
        assert "sources" in r.json()
    finally:
        for p in patches:
            p.stop()


def test_quality_monitor_smoke(client: TestClient) -> None:
    patches = _patch_db_helpers({})
    for p in patches:
        p.start()
    try:
        r = client.get("/api/observe/quality-monitor")
        assert r.status_code == 200
        assert "live" in r.json()
    finally:
        for p in patches:
            p.stop()


def test_geo_heatmap_smoke(client: TestClient) -> None:
    patches = _patch_db_helpers({})
    for p in patches:
        p.start()
    try:
        r = client.get("/api/observe/geo-heatmap?level=state")
        assert r.status_code == 200
        assert r.json()["level"] in ("country", "state")
    finally:
        for p in patches:
            p.stop()


def test_geo_heatmap_bad_level_400(client: TestClient) -> None:
    patches = _patch_db_helpers({})
    for p in patches:
        p.start()
    try:
        r = client.get("/api/observe/geo-heatmap?level=galaxy")
        # FastAPI rejects pattern-mismatch with 422
        assert r.status_code in (400, 422)
    finally:
        for p in patches:
            p.stop()


def test_story_pulse_smoke(client: TestClient) -> None:
    patches = _patch_db_helpers({})
    for p in patches:
        p.start()
    try:
        r = client.get("/api/observe/story-pulse?limit=5")
        assert r.status_code == 200
        assert "clusters" in r.json()
    finally:
        for p in patches:
            p.stop()


def test_crosstab_smoke(client: TestClient) -> None:
    patches = _patch_db_helpers({})
    for p in patches:
        p.start()
    try:
        r = client.get("/api/observe/crosstab?actor=Modi")
        assert r.status_code == 200
        assert "rows" in r.json()
    finally:
        for p in patches:
            p.stop()


def test_live_tail_smoke(client: TestClient) -> None:
    patches = _patch_db_helpers({})
    for p in patches:
        p.start()
    try:
        r = client.get("/api/observe/live-tail?limit=10")
        assert r.status_code == 200
        assert "articles" in r.json()
    finally:
        for p in patches:
            p.stop()


def test_audit_queue_smoke(client: TestClient) -> None:
    patches = _patch_db_helpers({})
    for p in patches:
        p.start()
    try:
        r = client.get("/api/observe/audit-queue")
        assert r.status_code == 200
        assert "queue" in r.json()
    finally:
        for p in patches:
            p.stop()


def test_audit_decision_validates_verdict(client: TestClient) -> None:
    r = client.post("/api/observe/audit-decision", json={
        "article_id": "00000000-0000-0000-0000-000000000000",
        "field_name": "primary_subject",
        "extraction_version": 3,
        "verdict": "garbage",
    })
    # Pydantic rejects the verdict pattern with 422
    assert r.status_code == 422


def test_audit_decision_writes(client: TestClient) -> None:
    with patch(
        "backend.routers.observe_router.record_decision",
        AsyncMock(return_value={"id": "abc-123", "decided_at": "2026-05-22T00:00:00Z"}),
    ):
        r = client.post("/api/observe/audit-decision", json={
            "article_id": "00000000-0000-0000-0000-000000000000",
            "field_name": "primary_subject",
            "extraction_version": 3,
            "verdict": "correct",
            "note": "looks good",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["id"] == "abc-123"
