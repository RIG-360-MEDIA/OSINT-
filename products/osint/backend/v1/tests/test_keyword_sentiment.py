"""Coverage for endpoints/keyword_sentiment.py — helpers + the on-demand route.

LLM (call_groq) and the DB are both mocked; no network / no DB.
"""
from __future__ import annotations

import datetime

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from _fakes import single_db  # noqa: E402

from v1 import scope as scopemod  # noqa: E402
from v1.auth import ApiPrincipal  # noqa: E402
from v1.endpoints import keyword_sentiment as ks  # noqa: E402
from v1.router import router as v1_router  # noqa: E402
from v1.scope import ApiContext, OrgScope  # noqa: E402

ORG = "11111111-1111-1111-1111-111111111111"


def _dt():
    return datetime.datetime(2026, 6, 30, 12, 0, tzinfo=datetime.timezone.utc)


def _ctx():
    return ApiContext(
        principal=ApiPrincipal(org_id=ORG, org_name="T", key_id="k", is_sandbox=False,
                               rate_limit_per_min=600, monthly_quota=None, can_manage=True),
        scope=OrgScope(ORG, True, (), (), (), (), (), (), {}))


@pytest.fixture()
def app():
    from v1.errors import GatewayError, gateway_error_handler
    a = FastAPI()
    a.add_exception_handler(GatewayError, gateway_error_handler)
    a.include_router(v1_router)
    a.dependency_overrides[scopemod.get_context] = _ctx
    return a


def _client(app):
    return TestClient(app)


# ── pure helpers ────────────────────────────────────────────────────────────

def test_norm_and_like_and_aggregate():
    assert ks._norm("Positive") == "positive"
    assert ks._norm("neg") == "negative"
    assert ks._norm("neutral vibes") == "neutral"
    assert ks._norm("not relevant", allow_nr=True) == "not_relevant"
    assert ks._norm("???") is None
    assert ks._like("a%b_c") == "%a\\%b\\_c%"
    empty = ks._aggregate([])
    assert empty["n_scored"] == 0 and empty["stance_score"] is None
    agg = ks._aggregate([("positive", "positive", 0.9), ("negative", "neutral", 0.5)])
    assert agg["n_scored"] == 2 and agg["stance"]["positive"] == 1


# ── cache hit path ──────────────────────────────────────────────────────────

def _cache_row():
    return {"n_matched": 10, "n_scored": 8, "capped": False,
            "stance_pos": 5, "stance_neg": 2, "stance_neu": 1,
            "impact_pos": 4, "impact_neg": 3, "impact_neu": 1, "impact_nr": 0,
            "stance_score": 0.3, "impact_score": 0.1, "model": "cached-model",
            "computed_at": _dt()}


def test_keyword_sentiment_cache_hit(app, monkeypatch):
    monkeypatch.setattr(ks, "get_db", single_db([[_cache_row()]]))
    r = _client(app).get("/v1/analytics/keyword-sentiment?keyword=ceasefire")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["cached"] is True and data["model"] == "cached-model"


# ── no-mentions path ────────────────────────────────────────────────────────

def test_keyword_sentiment_no_mentions(app, monkeypatch):
    # cache read miss ([]), then search returns [] -> "no mentions" note.
    monkeypatch.setattr(ks, "get_db", single_db([[], []]))
    r = _client(app).get("/v1/analytics/keyword-sentiment?keyword=zzznope&refresh=true")
    assert r.status_code == 200
    assert r.json()["data"]["note"].startswith("no mentions")


# ── full compute path (LLM mocked) ──────────────────────────────────────────

def test_keyword_sentiment_computes(app, monkeypatch):
    # refresh=true -> skip cache read; search returns rows; score each; write cache.
    rows = [{"id": "a1", "body": "Court fines the firm heavily", "published_at": _dt()},
            {"id": "a2", "body": "Firm wins a major award", "published_at": _dt()}]
    monkeypatch.setattr(ks, "get_db", single_db([rows, []]))

    async def fake_call_groq(*a, **k):
        return '{"stance":"negative","impact":"negative","impact_confidence":0.8}'

    monkeypatch.setattr(ks, "call_groq", fake_call_groq)
    r = _client(app).get("/v1/analytics/keyword-sentiment?keyword=acme&refresh=true")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["cached"] is False and data["n_scored"] == 2
    assert data["stance"]["negative"] == 2


def test_keyword_sentiment_score_handles_bad_json(app, monkeypatch):
    rows = [{"id": "a1", "body": "text", "published_at": _dt()}]
    monkeypatch.setattr(ks, "get_db", single_db([rows, []]))

    async def bad_groq(*a, **k):
        return "not json at all"

    monkeypatch.setattr(ks, "call_groq", bad_groq)
    r = _client(app).get("/v1/analytics/keyword-sentiment?keyword=acme&refresh=true")
    assert r.status_code == 200
    # unparseable -> no hits scored
    assert r.json()["data"]["n_scored"] == 0
