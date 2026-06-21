"""Integration tests for Bucket-2 endpoints: notes, brief schedule, channels.

Corpus-free (the /me/brief generation that hits the corpus is validated live)."""
from __future__ import annotations

import pytest

A_UUID = "123e4567-e89b-12d3-a456-426614174000"
B_UUID = "223e4567-e89b-12d3-a456-426614174000"


async def _signup(client, username):
    r = await client.post("/auth/signup", json={"username": username, "password": "secret123"})
    return r.json()["token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---- notes ----
@pytest.mark.asyncio
async def test_note_crud(client):
    tok = await _signup(client, "noter")
    n = await client.post("/notes", headers=_h(tok), json={"article_id": A_UUID, "body": "key quote here"})
    assert n.status_code == 200
    nid = n.json()["id"]
    lst = await client.get("/notes", headers=_h(tok))
    assert len(lst.json()) == 1
    d = await client.delete(f"/notes/{nid}", headers=_h(tok))
    assert d.status_code == 200
    assert (await client.get("/notes", headers=_h(tok))).json() == []


@pytest.mark.asyncio
async def test_note_filter_by_article(client):
    tok = await _signup(client, "noter2")
    await client.post("/notes", headers=_h(tok), json={"article_id": A_UUID, "body": "n1"})
    await client.post("/notes", headers=_h(tok), json={"article_id": B_UUID, "body": "n2"})
    only_a = await client.get("/notes", headers=_h(tok), params={"article_id": A_UUID})
    assert len(only_a.json()) == 1 and only_a.json()[0]["body"] == "n1"


@pytest.mark.asyncio
async def test_note_bad_uuid_422(client):
    tok = await _signup(client, "noter3")
    r = await client.post("/notes", headers=_h(tok), json={"article_id": "nope", "body": "x"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_notes_isolated_per_user(client):
    ta, tb = await _signup(client, "nalice"), await _signup(client, "nbob")
    await client.post("/notes", headers=_h(ta), json={"article_id": A_UUID, "body": "a-secret"})
    assert (await client.get("/notes", headers=_h(tb))).json() == []


# ---- brief schedule ----
@pytest.mark.asyncio
async def test_schedule_default_off_then_set(client):
    tok = await _signup(client, "sched")
    assert (await client.get("/me/brief/schedule", headers=_h(tok))).json()["cadence"] == "off"
    put = await client.put("/me/brief/schedule", headers=_h(tok),
                           json={"cadence": "daily", "hour_utc": 6, "languages": ["te"]})
    assert put.status_code == 200
    got = (await client.get("/me/brief/schedule", headers=_h(tok))).json()
    assert got["cadence"] == "daily" and got["hour_utc"] == 6 and got["languages"] == ["te"]


@pytest.mark.asyncio
async def test_schedule_hour_validation(client):
    tok = await _signup(client, "sched2")
    bad = await client.put("/me/brief/schedule", headers=_h(tok), json={"cadence": "daily", "hour_utc": 99})
    assert bad.status_code == 422


# ---- delivery channels ----
@pytest.mark.asyncio
async def test_channel_crud_and_webhook_validation(client):
    tok = await _signup(client, "chan")
    good = await client.post("/channels", headers=_h(tok), json={"kind": "webhook", "target": "https://hooks.x/abc"})
    assert good.status_code == 200
    bad = await client.post("/channels", headers=_h(tok), json={"kind": "webhook", "target": "not-a-url"})
    assert bad.status_code == 422
    assert len((await client.get("/channels", headers=_h(tok))).json()) == 1
    cid = good.json()["id"]
    assert (await client.delete(f"/channels/{cid}", headers=_h(tok))).status_code == 200


@pytest.mark.asyncio
async def test_brief_requires_auth(client):
    assert (await client.get("/me/brief")).status_code == 401
    assert (await client.get("/notes")).status_code == 401
