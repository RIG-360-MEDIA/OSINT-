"""Security + edge-case suite for the /v1 gateway.

Focus: the leak-safety and never-fail guarantees that don't need a live DB —
auth rejection, the scope gate, IDOR, field-whitelisting, cursor tampering,
filter validation, rate limiting, and the error envelope. DB-backed endpoint
behaviour is covered by integration tests (require a populated database).
"""
from __future__ import annotations

import os
import pathlib
import sys

os.environ.setdefault("OSINT_DB_URL", "postgresql+asyncpg://u:p@localhost/db")
os.environ.setdefault("OSINT_APIKEY_HASH_SECRET", "unit-test-secret")
os.environ.setdefault("OSINT_ENVIRONMENT", "development")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))  # backend/

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from v1 import install_v1, keys, ratelimit  # noqa: E402
from v1.auth import _extract_key  # noqa: E402
from v1.errors import GatewayError  # noqa: E402
from v1.filters import _coerce_uuids  # noqa: E402
from v1.pagination import decode_cursor, encode_cursor  # noqa: E402
from v1.scope import OrgScope, effective_entity_ids, require_entity_in_scope, require_region_in_scope  # noqa: E402
from v1.serializers import serialize_article, serialize_entity, serialize_sentiment  # noqa: E402


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    install_v1(app)
    return TestClient(app)


from starlette.datastructures import Headers  # noqa: E402


class _Req:
    """Minimal stand-in for a Starlette Request — real (case-insensitive) Headers."""

    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = Headers(headers)


# ── Auth: rejection paths (no DB needed) ────────────────────────────────────

def test_health_is_open(client: TestClient) -> None:
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "ok"


def test_no_key_is_401_with_envelope(client: TestClient) -> None:
    r = client.get("/v1/entities")
    assert r.status_code == 401
    body = r.json()
    assert body["error"]["code"] == "unauthorized"
    assert body["error"]["status"] == 401
    assert "WWW-Authenticate" in r.headers


def test_malformed_key_is_401(client: TestClient) -> None:
    for hdr in ["Bearer garbage", "Bearer rig_live_short", "Basic xyz", "Bearer "]:
        r = client.get("/v1/entities", headers={"Authorization": hdr})
        assert r.status_code == 401, hdr


def test_extract_key_variants() -> None:
    k = keys.generate_key()
    assert _extract_key(_Req({"Authorization": f"Bearer {k}"})) == k
    assert _extract_key(_Req({"authorization": f"bearer {k}"})) == k  # case-insensitive
    assert _extract_key(_Req({"X-API-Key": k})) == k
    assert _extract_key(_Req({})) is None
    assert _extract_key(_Req({"Authorization": "Bearer"})) is None
    assert _extract_key(_Req({"Authorization": "Basic abc"})) is None


def test_impersonate_header_is_ignored() -> None:
    # The API path never reads X-Impersonate — extraction returns only the key.
    k = keys.generate_key()
    req = _Req({"Authorization": f"Bearer {k}", "X-Impersonate": "00000000-0000-0000-0000-000000000000"})
    assert _extract_key(req) == k  # impersonation header has no effect


# ── Keys ────────────────────────────────────────────────────────────────────

def test_key_format_and_hash() -> None:
    live, sand = keys.generate_key(), keys.generate_key(sandbox=True)
    assert keys.is_well_formed(live) and keys.is_well_formed(sand)
    assert not keys.is_sandbox(live) and keys.is_sandbox(sand)
    assert keys.hash_key(live, "s") == keys.hash_key(live, "s")
    assert keys.hash_key(live, "s") != keys.hash_key(live, "t")
    assert len(keys.hash_key(live, "s")) == 64


@pytest.mark.parametrize("bad", [None, "", "x", "rig_live_short", "token_xyz", 123, "rig_live_" + "a" * 39])
def test_malformed_keys_rejected(bad) -> None:
    assert not keys.is_well_formed(bad)


# ── Scope gate + IDOR ───────────────────────────────────────────────────────

def test_effective_entity_ids_intersection() -> None:
    sc = OrgScope("o", False, ("e1", "e2", "e3"), (), (), ())
    # no request filter -> all scoped
    assert set(effective_entity_ids(sc, None)) == {"e1", "e2", "e3"}
    # request subset -> that subset
    assert set(effective_entity_ids(sc, ["e2"])) == {"e2"}
    # request OUTSIDE scope -> dropped (cannot widen)
    assert effective_entity_ids(sc, ["e9"]) == []
    assert set(effective_entity_ids(sc, ["e2", "e9"])) == {"e2"}


def test_effective_entity_ids_all_entities() -> None:
    sc = OrgScope("o", True, (), (), (), ())
    assert effective_entity_ids(sc, None) == []          # sentinel: no constraint
    assert set(effective_entity_ids(sc, ["e9"])) == {"e9"}  # all_entities honours request


def test_empty_scope_is_fail_safe() -> None:
    sc = OrgScope("o", False, (), (), (), ())
    assert sc.is_empty
    assert effective_entity_ids(sc, None) == []
    assert effective_entity_ids(sc, ["anything"]) == []


def test_require_entity_in_scope_idor() -> None:
    sc = OrgScope("o", False, ("e1",), (), (), ())
    assert require_entity_in_scope(sc, "e1") == "e1"
    with pytest.raises(GatewayError) as ei:
        require_entity_in_scope(sc, "e2")
    assert ei.value.status == 404 and ei.value.code == "not_found"


def test_require_region_in_scope_idor() -> None:
    sc = OrgScope("o", False, (), (), ("IN",), ())
    assert require_region_in_scope(sc, "IN") == "IN"
    with pytest.raises(GatewayError) as ei:
        require_region_in_scope(sc, "US")
    assert ei.value.status == 404


# ── Field whitelisting (no internal column ever leaks) ──────────────────────

def test_serialize_article_whitelist() -> None:
    row = {
        "id": "a1", "headline": "H", "summary": "s" * 600, "source": "Outlet",
        "language": "en", "url": "https://x", "published_at": None, "geo_primary": "IN",
        # internal columns that must NEVER surface:
        "collected_at": "INTERNAL", "labse_embedding": [1, 2, 3],
        "substrate_status": "processing", "source_id": "secret-uuid",
    }
    out = serialize_article(row)
    assert set(out) == {"id", "headline", "summary", "full_text", "source", "language", "url",
                        "geo", "story_id", "sentiment", "source_flags", "api_ready",
                        "published_at", "last_updated"}
    # sanity: whitelist matches the serializer's documented shape
    assert out["story_id"] is None and out["sentiment"] is None
    for leak in ("collected_at", "labse_embedding", "substrate_status", "source_id"):
        assert leak not in out
    assert len(out["summary"]) <= 400  # truncated


def test_serialize_entity_whitelist() -> None:
    row = {"id": "e1", "name": "N", "type": "person", "redirected_to": "x", "metadata": {"k": "v"}}
    out = serialize_entity(row)
    assert set(out) == {"id", "name", "type"}


def test_serialize_sentiment_shape() -> None:
    out = serialize_sentiment({"supportive": 3, "neutral": 5, "critical": 2, "total": 10, "net_lean": 0.1}, "X", 7)
    assert out["subject"] == "X" and out["window_days"] == 7
    assert out["split"] == {"supportive": 3, "neutral": 5, "critical": 2}
    assert "basis" in out  # honesty caveat present


# ── Cursor: roundtrip + tamper-proof ────────────────────────────────────────

def test_cursor_roundtrip() -> None:
    import datetime
    ts = datetime.datetime(2026, 6, 30, 12, 0, tzinfo=datetime.timezone.utc)
    cur = encode_cursor(ts, "11111111-1111-1111-1111-111111111111")
    t, i = decode_cursor(cur)
    assert i == "11111111-1111-1111-1111-111111111111"
    assert decode_cursor(None) is None


@pytest.mark.parametrize("bad", ["!!!", "abc", "eyJ0", "x" * 600, "////"])
def test_tampered_cursor_400(bad) -> None:
    with pytest.raises(GatewayError) as ei:
        decode_cursor(bad)
    assert ei.value.status == 400


# ── Filter coercion ─────────────────────────────────────────────────────────

def test_coerce_uuids_drops_garbage() -> None:
    good = "11111111-1111-1111-1111-111111111111"
    out = _coerce_uuids([good, "not-a-uuid", "", None, good])  # dup + junk
    assert out == (good,)  # deduped, junk dropped


# ── Rate limiting ───────────────────────────────────────────────────────────

def test_article_entities_empty_scope_returns_nothing() -> None:
    # C-1 regression: a non-all_entities org with no scope ids gets [] and never
    # touches the DB (db=None would raise if used) — so no out-of-scope entity
    # can ever be returned.
    import asyncio

    from v1 import queries
    assert asyncio.run(queries.article_entities(None, "aid", [], False)) == []


def test_derive_webhook_secret_deterministic_and_unstored() -> None:
    # H-6 regression: the signing secret is derived from the id (recomputable at
    # delivery), domain-separated, and stable — so nothing secret sits at rest.
    s1 = keys.derive_webhook_secret("wh-1", "server-secret")
    s2 = keys.derive_webhook_secret("wh-1", "server-secret")
    s3 = keys.derive_webhook_secret("wh-2", "server-secret")
    assert s1 == s2 and s1 != s3 and s1.startswith("whsec_")


def test_rate_limit_bucket_exhausts_and_blocks() -> None:
    ratelimit._buckets.pop("rk", None)
    results = [ratelimit._allow("rk", 3)[0] for _ in range(5)]
    assert results == [True, True, True, False, False]
    ok, remaining, retry = ratelimit._allow("rk", 3)
    assert ok is False and retry >= 1
