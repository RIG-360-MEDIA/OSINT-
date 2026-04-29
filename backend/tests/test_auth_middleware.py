"""
Tests for backend.auth.auth_middleware and the /api/me/access endpoint.

Strategy: monkeypatch the database access layer used inside the middleware
(`backend.auth.auth_middleware.get_db` and `backend.routers.me_router.get_db`)
with a FakeSession, so we never touch real Postgres. JWT signature verification
is left off (SUPABASE_JWT_SECRET not configured in tests) — the unverified
fallback path is exercised, matching test_brief_router.py's pattern.
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
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from backend.auth import auth_middleware as auth_module
from backend.auth.auth_middleware import (
    IMPERSONATION_COOKIE,
    get_current_principal,
    require_page,
    require_super_admin,
)
from backend.routers import me_router as me_module
from backend.routers.me_router import me_router


# ── Helpers ──────────────────────────────────────────────────────────────────

USER_ID = "11111111-1111-1111-1111-111111111111"
ADMIN_ID = "22222222-2222-2222-2222-222222222222"
TARGET_ID = "33333333-3333-3333-3333-333333333333"
SESSION_ID = "44444444-4444-4444-4444-444444444444"


def make_jwt(sub: str = USER_ID, email: str = "user@example.com", exp_offset: int = 3600) -> str:
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": sub, "email": email, "exp": int(time.time()) + exp_offset}).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.fake_sig"


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
    """Returns a queued FakeResult for each .execute() call.

    Pass `responses` as a list of result rows in the order the middleware
    will execute them. If a query is run with no queued response, an empty
    result is returned (so SELECT-style probes that find nothing don't blow up).
    """

    def __init__(self, responses: list[list[FakeRow]] | None = None) -> None:
        self._queue = list(responses or [])
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, query: Any, params: dict | None = None) -> FakeResult:
        self.calls.append((str(query), dict(params or {})))
        if self._queue:
            return FakeResult(self._queue.pop(0))
        return FakeResult([])

    async def commit(self) -> None:
        pass


def install_fake_db(monkeypatch: pytest.MonkeyPatch, session: FakeSession) -> None:
    """Patch get_db() in both modules to yield the same FakeSession."""

    @asynccontextmanager
    async def _fake_db():
        yield session

    monkeypatch.setattr(auth_module, "get_db", _fake_db)
    monkeypatch.setattr(me_module, "get_db", _fake_db)


def build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(me_router)

    @app.get("/protected/clips")
    async def _clips(_p: dict = Depends(require_page("clips"))) -> dict:
        return {"ok": True}

    @app.get("/admin-only")
    async def _admin(_p: dict = Depends(require_super_admin)) -> dict:
        return {"ok": True}

    return app


# ── Tests: token decoding & expiry ───────────────────────────────────────────

def test_missing_token_returns_401() -> None:
    app = build_app()
    client = TestClient(app)
    r = client.get("/api/me/access")
    assert r.status_code == 401


def test_expired_token_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession())
    app = build_app()
    client = TestClient(app)
    r = client.get(
        "/api/me/access",
        headers={"Authorization": f"Bearer {make_jwt(exp_offset=-10)}"},
    )
    assert r.status_code == 401
    assert "expired" in r.json()["detail"].lower()


def test_malformed_token_returns_401() -> None:
    app = build_app()
    client = TestClient(app)
    r = client.get(
        "/api/me/access",
        headers={"Authorization": "Bearer not.a.jwt.at.all"},
    )
    assert r.status_code == 401


# ── Tests: /api/me/access ────────────────────────────────────────────────────

def test_me_access_for_normal_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """User with role='user', two granted pages, has profile, has entities."""
    session = FakeSession([
        [FakeRow(role="user")],                                              # _resolve_role
        [FakeRow(page_slug="clips"), FakeRow(page_slug="signals")],          # allowed pages
        [FakeRow()],                                                         # has_profile
        [FakeRow()],                                                         # has_entities
    ])
    install_fake_db(monkeypatch, session)

    app = build_app()
    client = TestClient(app)
    r = client.get(
        "/api/me/access",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "user"
    assert body["allowed_pages"] == ["clips", "signals"]
    assert body["has_profile"] is True
    assert body["has_entities"] is True
    assert body["is_impersonating"] is False
    assert body["target_email"] is None


def test_me_access_for_super_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Super admins get all known pages without consulting user_page_access."""
    session = FakeSession([
        [FakeRow(role="super_admin")],   # _resolve_role
        [],                              # has_profile (none — should be False)
        [],                              # has_entities
    ])
    install_fake_db(monkeypatch, session)

    app = build_app()
    client = TestClient(app)
    r = client.get(
        "/api/me/access",
        headers={"Authorization": f"Bearer {make_jwt(sub=ADMIN_ID, email='admin@x.com')}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "super_admin"
    assert "clips" in body["allowed_pages"]
    assert "worldmonitor" in body["allowed_pages"]
    assert body["has_profile"] is False
    assert body["has_entities"] is False


# ── Tests: require_page ──────────────────────────────────────────────────────

def test_require_page_allows_when_granted(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession([
        [FakeRow(role="user")],   # _resolve_role inside get_current_principal
        [FakeRow(n=1)],           # _user_has_page returns a row
    ])
    install_fake_db(monkeypatch, session)

    app = build_app()
    client = TestClient(app)
    r = client.get("/protected/clips", headers={"Authorization": f"Bearer {make_jwt()}"})
    assert r.status_code == 200


def test_require_page_403_when_not_granted(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession([
        [FakeRow(role="user")],   # _resolve_role
        [],                       # _user_has_page returns nothing
    ])
    install_fake_db(monkeypatch, session)

    app = build_app()
    client = TestClient(app)
    r = client.get("/protected/clips", headers={"Authorization": f"Bearer {make_jwt()}"})
    assert r.status_code == 403
    body = r.json()
    assert body["detail"]["error"] == "page_forbidden"
    assert body["detail"]["page"] == "clips"


def test_require_page_super_admin_bypasses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Super admins skip the user_page_access lookup entirely."""
    session = FakeSession([
        [FakeRow(role="super_admin")],   # _resolve_role only
    ])
    install_fake_db(monkeypatch, session)

    app = build_app()
    client = TestClient(app)
    r = client.get("/protected/clips", headers={"Authorization": f"Bearer {make_jwt()}"})
    assert r.status_code == 200
    # And no follow-up _user_has_page query happened:
    assert len(session.calls) == 1


def test_require_page_unknown_slug_raises_at_build_time() -> None:
    with pytest.raises(ValueError):
        require_page("not-a-real-page")


# ── Tests: require_super_admin ───────────────────────────────────────────────

def test_require_super_admin_403_for_normal_user(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession([[FakeRow(role="user")]])
    install_fake_db(monkeypatch, session)

    app = build_app()
    client = TestClient(app)
    r = client.get("/admin-only", headers={"Authorization": f"Bearer {make_jwt()}"})
    assert r.status_code == 403


def test_require_super_admin_allows_super_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession([[FakeRow(role="super_admin")]])
    install_fake_db(monkeypatch, session)

    app = build_app()
    client = TestClient(app)
    r = client.get("/admin-only", headers={"Authorization": f"Bearer {make_jwt()}"})
    assert r.status_code == 200


# ── Tests: impersonation cookie ──────────────────────────────────────────────

def test_impersonation_only_works_for_super_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-admin presenting the cookie is silently ignored."""
    session = FakeSession([
        [FakeRow(role="user")],  # _resolve_role — not super_admin, cookie ignored
        [FakeRow(page_slug="clips")],  # allowed pages
        [FakeRow()],                    # has_profile
        [FakeRow()],                    # has_entities
    ])
    install_fake_db(monkeypatch, session)

    app = build_app()
    client = TestClient(app)
    client.cookies.set(IMPERSONATION_COOKIE, SESSION_ID)
    r = client.get(
        "/api/me/access",
        headers={"Authorization": f"Bearer {make_jwt()}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["is_impersonating"] is False
    assert body["user_id"] == USER_ID


def test_impersonation_resolves_target_for_super_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valid cookie + super_admin caller → effective principal is the target."""
    session = FakeSession([
        [FakeRow(role="super_admin")],  # _resolve_role
        [FakeRow(                        # _resolve_impersonation
            id=SESSION_ID,
            target_user_id=TARGET_ID,
            target_email="target@example.com",
        )],
        # super_admin path skips the page lookup; profile + entities are still checked
        [FakeRow()],   # has_profile (target)
        [FakeRow()],   # has_entities (target)
    ])
    install_fake_db(monkeypatch, session)

    app = build_app()
    client = TestClient(app)
    client.cookies.set(IMPERSONATION_COOKIE, SESSION_ID)
    r = client.get(
        "/api/me/access",
        headers={"Authorization": f"Bearer {make_jwt(sub=ADMIN_ID, email='admin@x.com')}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["is_impersonating"] is True
    assert body["user_id"] == TARGET_ID
    assert body["email"] == "target@example.com"
    assert body["real_email"] == "admin@x.com"
    assert body["target_email"] == "target@example.com"


def test_impersonation_invalid_cookie_falls_back_to_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """A malformed cookie does not break the request — admin acts as themself."""
    session = FakeSession([
        [FakeRow(role="super_admin")],   # _resolve_role
        # _resolve_impersonation is short-circuited by _is_valid_uuid before any query.
        [],                              # has_profile
        [],                              # has_entities
    ])
    install_fake_db(monkeypatch, session)

    app = build_app()
    client = TestClient(app)
    client.cookies.set(IMPERSONATION_COOKIE, "not-a-uuid")
    r = client.get(
        "/api/me/access",
        headers={"Authorization": f"Bearer {make_jwt(sub=ADMIN_ID, email='admin@x.com')}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["is_impersonating"] is False
    assert body["user_id"] == ADMIN_ID
