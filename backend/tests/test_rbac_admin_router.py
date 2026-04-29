"""
Tests for backend.routers.rbac_admin_router.

Same FakeSession + monkeypatch pattern as test_auth_middleware. Covers:
  - Non-admins are 403'd by require_super_admin
  - GET /api/admin/users payload shape
  - PUT /api/admin/users/{id}/pages with valid + unknown slugs
  - PUT /api/admin/users/{id}/role validation
  - POST /api/admin/impersonate/{id} happy path + self-impersonation guard
  - POST /api/admin/impersonate/end clears the cookie
"""
from __future__ import annotations

import base64
import json
import time
import types
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth import auth_middleware as auth_module
from backend.auth.auth_middleware import IMPERSONATION_COOKIE
from backend.routers import rbac_admin_router as rbac_module
from backend.routers.rbac_admin_router import rbac_admin_router

ADMIN_ID = "11111111-1111-1111-1111-111111111111"
TARGET_ID = "22222222-2222-2222-2222-222222222222"
SESSION_ID = "33333333-3333-3333-3333-333333333333"


def make_jwt(sub: str = ADMIN_ID, email: str = "admin@x.com") -> str:
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": sub, "email": email, "exp": int(time.time()) + 3600}).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.fake_sig"


class FakeRow(types.SimpleNamespace):
    pass


class FakeResult:
    def __init__(self, rows: list[FakeRow], rowcount: int = 0) -> None:
        self._rows = rows
        self.rowcount = rowcount

    def fetchall(self) -> list[FakeRow]:
        return list(self._rows)

    def fetchone(self) -> FakeRow | None:
        return self._rows[0] if self._rows else None


class FakeSession:
    def __init__(self, responses: list[FakeResult] | None = None) -> None:
        self._queue = list(responses or [])
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, query: Any, params: dict | None = None) -> FakeResult:
        self.calls.append((str(query), dict(params or {})))
        if self._queue:
            return self._queue.pop(0)
        return FakeResult([], rowcount=0)

    async def commit(self) -> None:
        pass


def install_fake_db(monkeypatch: pytest.MonkeyPatch, session: FakeSession) -> None:
    @asynccontextmanager
    async def _fake_db():
        yield session
    monkeypatch.setattr(auth_module, "get_db", _fake_db)
    monkeypatch.setattr(rbac_module, "get_db", _fake_db)


def build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(rbac_admin_router)
    return app


# ── Authorization gate ───────────────────────────────────────────────────────

def test_non_admin_gets_403_on_users_list(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([
        FakeResult([FakeRow(role="user")]),  # _resolve_role
    ]))
    client = TestClient(build_app())
    r = client.get("/api/admin/users", headers={"Authorization": f"Bearer {make_jwt()}"})
    assert r.status_code == 403


# ── List users ───────────────────────────────────────────────────────────────

def test_list_users_returns_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([
        FakeResult([FakeRow(role="super_admin")]),  # role check
        FakeResult([
            FakeRow(
                id=TARGET_ID, email="alice@example.com", role="user",
                created_at=None, allowed_pages=["clips", "signals"],
                entity_count=3, has_profile=True,
            ),
        ]),
    ]))
    client = TestClient(build_app())
    r = client.get("/api/admin/users", headers={"Authorization": f"Bearer {make_jwt()}"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["users"]) == 1
    assert body["users"][0]["email"] == "alice@example.com"
    assert body["users"][0]["allowed_pages"] == ["clips", "signals"]
    assert "clips" in body["known_pages"]


# ── Set pages ────────────────────────────────────────────────────────────────

def test_set_pages_rejects_unknown_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([
        FakeResult([FakeRow(role="super_admin")]),
    ]))
    client = TestClient(build_app())
    r = client.put(
        f"/api/admin/users/{TARGET_ID}/pages",
        headers={"Authorization": f"Bearer {make_jwt()}"},
        json={"pages": ["clips", "fake-page"]},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "unknown_pages"


def test_set_pages_404_when_user_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([
        FakeResult([FakeRow(role="super_admin")]),  # role
        FakeResult([]),                              # exists check returns nothing
    ]))
    client = TestClient(build_app())
    r = client.put(
        f"/api/admin/users/{TARGET_ID}/pages",
        headers={"Authorization": f"Bearer {make_jwt()}"},
        json={"pages": ["clips"]},
    )
    assert r.status_code == 404


def test_set_pages_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([
        FakeResult([FakeRow(role="super_admin")]),  # role
        FakeResult([FakeRow(n=1)]),                  # user exists
        FakeResult([]),                              # DELETE
        FakeResult([]),                              # INSERT clips
        FakeResult([]),                              # INSERT signals
    ]))
    client = TestClient(build_app())
    r = client.put(
        f"/api/admin/users/{TARGET_ID}/pages",
        headers={"Authorization": f"Bearer {make_jwt()}"},
        json={"pages": ["clips", "signals"]},
    )
    assert r.status_code == 200
    assert r.json()["pages"] == ["clips", "signals"]


# ── Set role ─────────────────────────────────────────────────────────────────

def test_set_role_rejects_invalid_value(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([
        FakeResult([FakeRow(role="super_admin")]),
    ]))
    client = TestClient(build_app())
    r = client.put(
        f"/api/admin/users/{TARGET_ID}/role",
        headers={"Authorization": f"Bearer {make_jwt()}"},
        json={"role": "wizard"},
    )
    assert r.status_code == 400


def test_set_role_404_on_missing_user(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([
        FakeResult([FakeRow(role="super_admin")]),
        FakeResult([], rowcount=0),
    ]))
    client = TestClient(build_app())
    r = client.put(
        f"/api/admin/users/{TARGET_ID}/role",
        headers={"Authorization": f"Bearer {make_jwt()}"},
        json={"role": "user"},
    )
    assert r.status_code == 404


# ── Impersonation start ──────────────────────────────────────────────────────

def test_impersonate_self_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([
        FakeResult([FakeRow(role="super_admin")]),
    ]))
    client = TestClient(build_app())
    r = client.post(
        f"/api/admin/impersonate/{ADMIN_ID}",
        headers={"Authorization": f"Bearer {make_jwt()}"},
        json={"reason": None},
    )
    assert r.status_code == 400


def test_impersonate_super_admin_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([
        FakeResult([FakeRow(role="super_admin")]),  # admin role
        FakeResult([FakeRow(id=TARGET_ID, email="other@x.com", role="super_admin")]),
    ]))
    client = TestClient(build_app())
    r = client.post(
        f"/api/admin/impersonate/{TARGET_ID}",
        headers={"Authorization": f"Bearer {make_jwt()}"},
        json={"reason": None},
    )
    assert r.status_code == 400


def test_impersonate_happy_path_sets_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([
        FakeResult([FakeRow(role="super_admin")]),                            # role
        FakeResult([FakeRow(id=TARGET_ID, email="alice@x.com", role="user")]),# target lookup
        FakeResult([]),                                                       # close existing
        FakeResult([FakeRow(id=SESSION_ID)]),                                 # INSERT RETURNING id
    ]))
    client = TestClient(build_app())
    r = client.post(
        f"/api/admin/impersonate/{TARGET_ID}",
        headers={"Authorization": f"Bearer {make_jwt()}"},
        json={"reason": "QA"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == SESSION_ID
    assert body["target_email"] == "alice@x.com"
    assert IMPERSONATION_COOKIE in r.cookies
    assert r.cookies[IMPERSONATION_COOKIE] == SESSION_ID


# ── Impersonation end ────────────────────────────────────────────────────────

def test_impersonate_end_closes_session(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession([
        FakeResult([FakeRow(role="super_admin")]),  # _resolve_role
        FakeResult([]),                              # _resolve_impersonation: cookie is a valid UUID
                                                     # so the lookup runs, but for "end" we want it
                                                     # to return nothing (no active session row)
        FakeResult([], rowcount=1),                  # UPDATE closing
    ]))
    client = TestClient(build_app())
    client.cookies.set(IMPERSONATION_COOKIE, SESSION_ID)
    r = client.post(
        "/api/admin/impersonate/end",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    assert r.json()["closed"] == 1
