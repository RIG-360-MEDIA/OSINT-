"""Endpoint coverage for admin.py — super-admin key/scope administration."""
from __future__ import annotations

import datetime

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from _fakes import single_db  # noqa: E402

from v1 import admin  # noqa: E402
from v1.router import router as v1_router  # noqa: E402

ORG = "11111111-1111-1111-1111-111111111111"
ADMIN = "99999999-9999-9999-9999-999999999999"


def _dt():
    return datetime.datetime(2026, 6, 30, 12, 0, tzinfo=datetime.timezone.utc)


@pytest.fixture()
def app():
    from auth.middleware import require_super_admin
    from v1.errors import GatewayError, gateway_error_handler
    a = FastAPI()
    a.add_exception_handler(GatewayError, gateway_error_handler)
    a.include_router(v1_router)
    a.dependency_overrides[require_super_admin] = lambda: {"id": ADMIN}
    return a


def _client(app):
    return TestClient(app, raise_server_exceptions=True)


def test_create_key_success(app, monkeypatch):
    # execute #1: org exists check; #2: INSERT RETURNING id, created_at
    monkeypatch.setattr(admin, "get_db",
                        single_db([[{"n": 1}], [{"id": "k1", "created_at": _dt()}]]))
    r = _client(app).post("/v1/admin/keys", json={"org_id": ORG, "label": "x"})
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["id"] == "k1" and body["key"].startswith("rig_live_")


def test_create_key_bad_org(app, monkeypatch):
    monkeypatch.setattr(admin, "get_db", single_db([]))
    r = _client(app).post("/v1/admin/keys", json={"org_id": "not-a-uuid"})
    assert r.status_code == 400


def test_create_key_org_not_found(app, monkeypatch):
    monkeypatch.setattr(admin, "get_db", single_db([[]]))  # org check returns nothing
    r = _client(app).post("/v1/admin/keys", json={"org_id": ORG})
    assert r.status_code == 404


def test_list_keys(app, monkeypatch):
    rows = [[{"id": "k1", "key_prefix": "rig_live_ab", "label": "L", "is_sandbox": False,
              "rate_limit_per_min": 120, "monthly_quota": None, "created_at": _dt(),
              "last_used_at": None, "revoked_at": None, "expires_at": None}]]
    monkeypatch.setattr(admin, "get_db", single_db(rows))
    r = _client(app).get(f"/v1/admin/keys?org_id={ORG}")
    assert r.status_code == 200 and r.json()["meta"]["count"] == 1
    assert r.json()["data"][0]["revoked"] is False


def test_list_keys_bad_org(app, monkeypatch):
    monkeypatch.setattr(admin, "get_db", single_db([]))
    assert _client(app).get("/v1/admin/keys?org_id=bad").status_code == 400


def test_revoke_key(app, monkeypatch):
    monkeypatch.setattr(admin, "get_db", single_db([[{"x": 1}]]))  # rowcount 1
    r = _client(app).post(f"/v1/admin/keys/{ORG}/revoke")
    assert r.status_code == 200 and r.json()["data"]["revoked"] is True
    assert r.json()["data"]["was_already_revoked"] is False


def test_revoke_key_bad_id(app, monkeypatch):
    monkeypatch.setattr(admin, "get_db", single_db([]))
    assert _client(app).post("/v1/admin/keys/bad/revoke").status_code == 404


def test_set_scope(app, monkeypatch):
    monkeypatch.setattr(admin, "get_db", single_db([[{"n": 1}], []]))
    r = _client(app).put(f"/v1/admin/scope/{ORG}", json={
        "all_entities": False, "entity_ids": [ORG], "topics": ["POL"],
        "regions": ["TG"], "languages": ["en"]})
    assert r.status_code == 200
    assert r.json()["data"]["entity_ids"] == [ORG]


def test_set_scope_bad_org(app, monkeypatch):
    monkeypatch.setattr(admin, "get_db", single_db([]))
    assert _client(app).put("/v1/admin/scope/bad", json={}).status_code == 400


def test_set_scope_bad_entity(app, monkeypatch):
    monkeypatch.setattr(admin, "get_db", single_db([[{"n": 1}]]))
    r = _client(app).put(f"/v1/admin/scope/{ORG}", json={"entity_ids": ["not-a-uuid"]})
    assert r.status_code == 400


def test_set_scope_org_not_found(app, monkeypatch):
    monkeypatch.setattr(admin, "get_db", single_db([[]]))
    assert _client(app).put(f"/v1/admin/scope/{ORG}", json={}).status_code == 404


def test_get_scope_provisioned(app, monkeypatch):
    rows = [[{"all_entities": True, "entity_ids": [ORG], "topics": ["POL"],
              "regions": ["TG"], "languages": ["en"], "updated_at": _dt()}]]
    monkeypatch.setattr(admin, "get_db", single_db(rows))
    r = _client(app).get(f"/v1/admin/scope/{ORG}")
    assert r.status_code == 200 and r.json()["data"]["provisioned"] is True


def test_get_scope_unprovisioned(app, monkeypatch):
    monkeypatch.setattr(admin, "get_db", single_db([[]]))
    r = _client(app).get(f"/v1/admin/scope/{ORG}")
    assert r.status_code == 200 and r.json()["data"]["provisioned"] is False


def test_get_scope_bad_org(app, monkeypatch):
    monkeypatch.setattr(admin, "get_db", single_db([]))
    assert _client(app).get("/v1/admin/scope/bad").status_code == 400
