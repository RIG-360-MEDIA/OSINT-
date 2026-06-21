"""Integration tests for Set 2 account + personalization endpoints.

Corpus-free: every flow here is pure app-DB. Uses the ASGI `client` fixture
(temp SQLite). Validates routing, auth, CRUD, validation, and per-user isolation.
"""
from __future__ import annotations

import pytest


async def _signup(client, username, password="secret123"):
    r = await client.post("/auth/signup", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- auth
@pytest.mark.asyncio
async def test_signup_returns_token(client):
    r = await client.post("/auth/signup", json={"username": "aryan", "password": "secret123"})
    assert r.status_code == 200
    body = r.json()
    assert body["token"] and body["username"] == "aryan" and body["user_id"]


@pytest.mark.asyncio
async def test_signup_duplicate_username_409(client):
    await _signup(client, "dup")
    r = await client.post("/auth/signup", json={"username": "dup", "password": "secret123"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_signup_validation(client):
    r = await client.post("/auth/signup", json={"username": "ab", "password": "x"})
    assert r.status_code == 422  # username too short + password too short


@pytest.mark.asyncio
async def test_login_success_and_wrong_password(client):
    await _signup(client, "loginu", "rightpass")
    ok = await client.post("/auth/login", json={"username": "loginu", "password": "rightpass"})
    assert ok.status_code == 200 and ok.json()["token"]
    bad = await client.post("/auth/login", json={"username": "loginu", "password": "wrongpass"})
    assert bad.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_auth(client):
    assert (await client.get("/me")).status_code == 401
    assert (await client.get("/me", headers={"Authorization": "Bearer garbage"})).status_code == 401


@pytest.mark.asyncio
async def test_me_with_token(client):
    tok = await _signup(client, "meuser")
    r = await client.get("/me", headers=_h(tok))
    assert r.status_code == 200 and r.json()["username"] == "meuser"


@pytest.mark.asyncio
async def test_patch_me_default_languages(client):
    tok = await _signup(client, "prefs")
    r = await client.patch("/me", headers=_h(tok), json={"default_languages": ["te", "hi"], "home_geo": "Telangana"})
    assert r.status_code == 200
    body = r.json()
    assert body["default_languages"] == ["te", "hi"] and body["home_geo"] == "Telangana"


# ---------------------------------------------------------------- saved searches
@pytest.mark.asyncio
async def test_saved_search_crud(client):
    tok = await _signup(client, "saver")
    c = await client.post("/saved", headers=_h(tok), json={"name": "farmers", "query": "farmer loan waiver"})
    assert c.status_code == 200
    sid = c.json()["id"]
    lst = await client.get("/saved", headers=_h(tok))
    assert lst.status_code == 200 and len(lst.json()) == 1
    d = await client.delete(f"/saved/{sid}", headers=_h(tok))
    assert d.status_code == 200
    assert len((await client.get("/saved", headers=_h(tok))).json()) == 0


@pytest.mark.asyncio
async def test_saved_search_duplicate_name_409(client):
    tok = await _signup(client, "saver2")
    await client.post("/saved", headers=_h(tok), json={"name": "x", "query": "metro"})
    dup = await client.post("/saved", headers=_h(tok), json={"name": "x", "query": "other"})
    assert dup.status_code == 409


# ---------------------------------------------------------------- mutes
@pytest.mark.asyncio
async def test_mutes_crud_and_duplicate(client):
    tok = await _signup(client, "muter")
    m = await client.post("/mutes", headers=_h(tok), json={"kind": "source", "value": "spammy-outlet"})
    assert m.status_code == 200
    dup = await client.post("/mutes", headers=_h(tok), json={"kind": "source", "value": "spammy-outlet"})
    assert dup.status_code == 409
    lst = await client.get("/mutes", headers=_h(tok))
    assert len(lst.json()) == 1
    d = await client.delete(f"/mutes/{m.json()['id']}", headers=_h(tok))
    assert d.status_code == 200


@pytest.mark.asyncio
async def test_entity_mute_requires_uuid(client):
    tok = await _signup(client, "emuter")
    r = await client.post("/mutes", headers=_h(tok), json={"kind": "entity", "value": "not-a-uuid"})
    assert r.status_code == 422


# ---------------------------------------------------------------- watched entities
@pytest.mark.asyncio
async def test_watch_crud_with_name(client):
    tok = await _signup(client, "watcher")
    eid = "123e4567-e89b-12d3-a456-426614174000"
    w = await client.post("/watch", headers=_h(tok), json={"entity_id": eid, "canonical_name": "Narendra Modi"})
    assert w.status_code == 200 and w.json()["canonical_name"] == "Narendra Modi"
    dup = await client.post("/watch", headers=_h(tok), json={"entity_id": eid, "canonical_name": "Narendra Modi"})
    assert dup.status_code == 409
    lst = await client.get("/watch", headers=_h(tok))
    assert len(lst.json()) == 1
    d = await client.delete(f"/watch/{w.json()['id']}", headers=_h(tok))
    assert d.status_code == 200


@pytest.mark.asyncio
async def test_watch_bad_uuid(client):
    tok = await _signup(client, "watcher2")
    r = await client.post("/watch", headers=_h(tok), json={"entity_id": "nope", "canonical_name": "X"})
    assert r.status_code == 422


# ---------------------------------------------------------------- history
@pytest.mark.asyncio
async def test_history_empty_then_listed(client):
    tok = await _signup(client, "hist")
    r = await client.get("/me/history", headers=_h(tok))
    assert r.status_code == 200 and r.json() == []


# ---------------------------------------------------------------- isolation (critical)
@pytest.mark.asyncio
async def test_per_user_isolation(client):
    tok_a = await _signup(client, "alice")
    tok_b = await _signup(client, "bob")
    await client.post("/saved", headers=_h(tok_a), json={"name": "a-search", "query": "alice topic"})
    await client.post("/mutes", headers=_h(tok_b), json={"kind": "language", "value": "ta"})
    # bob sees none of alice's saved searches
    assert (await client.get("/saved", headers=_h(tok_b))).json() == []
    # alice sees none of bob's mutes
    assert (await client.get("/mutes", headers=_h(tok_a))).json() == []
    # alice cannot delete bob's mute (404, not 200)
    bob_mute_id = (await client.get("/mutes", headers=_h(tok_b))).json()[0]["id"]
    assert (await client.delete(f"/mutes/{bob_mute_id}", headers=_h(tok_a))).status_code == 404


@pytest.mark.asyncio
async def test_ask_works_anonymously_is_unpersonalized(client, monkeypatch):
    # /ask must still work with no auth; personalized=False, no history written.
    # Stub the corpus + answer path so this stays corpus-free.
    import app.main as m

    async def fake_retrieve(*a, **k):
        return []

    monkeypatch.setattr(m, "retrieve_and_curate", fake_retrieve)
    monkeypatch.setattr(m, "get_embedder", lambda: type("E", (), {"embed": lambda self, q: [0.0]})())

    class _Conn:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(m, "connect", lambda s: _Conn())
    r = await client.post("/ask", json={"query": "anything", "answer": False})
    assert r.status_code == 200
    assert r.json()["personalized"] is False and r.json()["web_used"] is False
