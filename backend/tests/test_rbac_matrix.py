"""End-to-end RBAC matrix probe.

Verifies, for every gated router and every (role, page-grant-state)
combination, that the page gate returns the correct status.

This is regression protection. The shipped fixes in the auth-rbac audit
added ``Depends(require_page("<slug>"))`` to clips, clippings,
newspapers, signals, and analyst routers; this test makes sure none of
those gates accidentally regress (e.g., someone reverts the dependency
during a routine change).

Strategy: same FakeSession + monkeypatch pattern used by
``test_auth_middleware`` so we never hit a real database.
"""
from __future__ import annotations

import base64
import json
import time
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── Reuse the FakeSession harness from test_auth_middleware ────────────────────

from backend.tests.test_auth_middleware import (  # type: ignore[import-not-found]
    FakeRow,
    FakeSession,
    install_fake_db,
)


USER_ID = "11111111-1111-1111-1111-111111111111"
EMAIL = "matrix-user@example.com"


def _mint_unsigned_jwt(user_id: str = USER_ID, email: str = EMAIL) -> str:
    """Mint an unsigned JWT — works because tests run with no JWT secret set,
    so auth_middleware._decode_unverified is used."""
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode()
    payload = json.dumps(
        {"sub": user_id, "email": email, "exp": int(time.time()) + 3600}
    ).encode()
    body = base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
    return f"{header}.{body}.unsigned"


def _build_app_with_router(router: Any) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


# ── Page-gate enforcement matrix ──────────────────────────────────────────────
#
# For each row: (router-attr, mounted-prefix, sample-endpoint-path, slug).
# The sample endpoint is one we know exists on the router.
GATED_ROUTERS: list[tuple[str, str, str]] = [
    ("backend.routers.clips_router:clips_router",        "/api/clips/feed",          "clips"),
    ("backend.routers.clippings_router:clippings_router","/api/clippings/feed",      "cuttings"),
    ("backend.routers.clippings_router:newspapers_router","/api/newspapers/0/pdf",   "cuttings"),
    ("backend.routers.signals_router:signals_router",    "/api/signals/feed",        "signals"),
    ("backend.routers.analyst_router:analyst_router",    "/api/analyst/session",     "analyst"),
    ("backend.routers.coverage_router:coverage_router",  "/api/coverage/feed",       "coverage"),
    ("backend.routers.documents_router:documents_router","/api/documents/feed",      "documents"),
    ("backend.routers.thread_router:thread_router",      "/api/threads/",            "threads"),
    ("backend.routers.worldmonitor_router:worldmonitor_router",
        "/api/worldmonitor/telangana/briefing",                                       "worldmonitor"),
    ("backend.routers.brief_router:brief_router",        "/api/brief/today",         "brief"),
    ("backend.routers.cm_router:cm_router",              "/api/cm/pulse",            "worldmonitor"),
]


def _import_router(spec: str) -> Any:
    module_path, attr = spec.split(":")
    import importlib
    return getattr(importlib.import_module(module_path), attr)


@pytest.mark.parametrize("router_spec,endpoint,slug", GATED_ROUTERS)
def test_page_gate_403_when_user_lacks_grant(
    monkeypatch: pytest.MonkeyPatch,
    router_spec: str,
    endpoint: str,
    slug: str,
) -> None:
    """A regular user with NO row in user_page_access for `slug` must get 403."""
    install_fake_db(monkeypatch, FakeSession([
        # _resolve_role -> 'user'
        [FakeRow(role="user")],
        # _user_has_page -> no row
        [],
    ]))

    router = _import_router(router_spec)
    # raise_server_exceptions=False so an unrelated 500 (e.g. the handler
    # hits FakeSession with an unexpected query AFTER passing the gate) is
    # surfaced as r.status_code instead of bubbling to pytest. The gate
    # outcome is what we're testing, not the handler's data path.
    client = TestClient(_build_app_with_router(router), raise_server_exceptions=False)
    r = client.get(endpoint, headers={"Authorization": f"Bearer {_mint_unsigned_jwt()}"})

    assert r.status_code == 403, (
        f"{endpoint} for slug={slug}: expected 403 (page_forbidden), got {r.status_code}: {r.text[:200]}"
    )
    body = r.json()
    assert body.get("detail", {}).get("error") == "page_forbidden", (
        f"{endpoint}: unexpected 403 body shape: {body}"
    )
    assert body["detail"]["page"] == slug, (
        f"{endpoint}: gate reported wrong slug: {body}"
    )


@pytest.mark.parametrize("router_spec,endpoint,slug", GATED_ROUTERS)
def test_page_gate_super_admin_bypasses(
    monkeypatch: pytest.MonkeyPatch,
    router_spec: str,
    endpoint: str,
    slug: str,
) -> None:
    """A super_admin always passes the page gate, regardless of grants.

    We don't assert 200 here — the actual endpoint may need DB rows we
    haven't seeded — but we do assert it's NOT 403 page_forbidden. That's
    what proves the gate let them through.
    """
    install_fake_db(monkeypatch, FakeSession(
        # _resolve_role returns super_admin; remaining queries return empty.
        [[FakeRow(role="super_admin")]] + [[] for _ in range(50)]
    ))

    router = _import_router(router_spec)
    # raise_server_exceptions=False so an unrelated 500 (e.g. the handler
    # hits FakeSession with an unexpected query AFTER passing the gate) is
    # surfaced as r.status_code instead of bubbling to pytest. The gate
    # outcome is what we're testing, not the handler's data path.
    client = TestClient(_build_app_with_router(router), raise_server_exceptions=False)
    r = client.get(endpoint, headers={"Authorization": f"Bearer {_mint_unsigned_jwt()}"})

    if r.status_code == 403:
        body = r.json()
        assert body.get("detail", {}).get("error") != "page_forbidden", (
            f"{endpoint}: super_admin was 403'd by page gate — gate is broken: {body}"
        )


def test_unauthenticated_request_to_gated_endpoint_returns_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No Authorization header → 401 from get_current_user, regardless of slug."""
    install_fake_db(monkeypatch, FakeSession([]))
    router = _import_router("backend.routers.clips_router:clips_router")
    # raise_server_exceptions=False so an unrelated 500 (e.g. the handler
    # hits FakeSession with an unexpected query AFTER passing the gate) is
    # surfaced as r.status_code instead of bubbling to pytest. The gate
    # outcome is what we're testing, not the handler's data path.
    client = TestClient(_build_app_with_router(router), raise_server_exceptions=False)
    r = client.get("/api/clips/feed")
    assert r.status_code == 401
