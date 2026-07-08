"""HTTP-level coverage for v1/endpoints/* with the scope dependency overridden.

We install the full router, override ``get_context`` so no auth/DB is needed to
reach a handler body, and monkeypatch each endpoint module's ``get_db`` to a
fake yielding canned rows. Both happy paths and empty-scope / 404 branches.
"""
from __future__ import annotations

import datetime

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from _fakes import single_db  # noqa: E402

from v1 import scope as scopemod  # noqa: E402
from v1.auth import ApiPrincipal  # noqa: E402
from v1.endpoints import (  # noqa: E402
    analytics, articles, brief, entities, geo, stories, usage, webhooks,
)
from v1.endpoints import scope as scope_ep  # noqa: E402
from v1.router import router as v1_router  # noqa: E402
from v1.scope import ApiContext, OrgScope  # noqa: E402

EID = "11111111-1111-1111-1111-111111111111"
EID2 = "22222222-2222-2222-2222-222222222222"
AID = "33333333-3333-3333-3333-333333333333"
SID = "44444444-4444-4444-4444-444444444444"


def _dt():
    return datetime.datetime(2026, 6, 30, 12, 0, tzinfo=datetime.timezone.utc)


def _principal(can_manage=True):
    return ApiPrincipal(org_id=EID, org_name="T", key_id="k", is_sandbox=False,
                        rate_limit_per_min=600, monthly_quota=None, can_manage=can_manage)


def _ctx(scope: OrgScope, can_manage=True):
    return ApiContext(principal=_principal(can_manage), scope=scope)


def _scope(all_entities=False, entity_ids=(EID,), regions=("Karnataka",),
           mute=("mute",), can_manage=True):
    return OrgScope(EID, all_entities, tuple(entity_ids), (), tuple(regions),
                    (), tuple(mute), (), {})


@pytest.fixture()
def app():
    from v1.errors import GatewayError, gateway_error_handler
    a = FastAPI()
    a.add_exception_handler(GatewayError, gateway_error_handler)
    a.include_router(v1_router)
    return a


def _override(app, scope, can_manage=True):
    app.dependency_overrides[scopemod.get_context] = lambda: _ctx(scope, can_manage)


def _client(app):
    return TestClient(app)


# ── entities ────────────────────────────────────────────────────────────────

def test_list_entities(app, monkeypatch):
    _override(app, _scope())
    monkeypatch.setattr(entities, "get_db",
                        single_db([[{"id": EID, "name": "N", "type": "person"}]]))
    r = _client(app).get("/v1/entities")
    assert r.status_code == 200 and r.json()["meta"]["count"] == 1


def test_get_entity_happy(app, monkeypatch):
    _override(app, _scope())
    # get_entity_row, entity_coverage_count, sentiment_split
    monkeypatch.setattr(entities, "get_db", single_db([
        [{"id": EID, "name": "N", "type": "person"}],
        [{"n": 5}],
        [{"stance": "critical", "n": 2}],
    ]))
    r = _client(app).get(f"/v1/entities/{EID}")
    assert r.status_code == 200
    assert r.json()["data"]["snapshot"]["coverage_7d"] == 5


def test_get_entity_bad_uuid(app):
    _override(app, _scope())
    assert _client(app).get("/v1/entities/not-a-uuid").status_code == 404


def test_get_entity_out_of_scope(app):
    _override(app, _scope(entity_ids=(EID,)))
    assert _client(app).get(f"/v1/entities/{EID2}").status_code == 404


def test_entity_coverage(app, monkeypatch):
    _override(app, _scope())
    monkeypatch.setattr(entities, "get_db", single_db([
        [{"type": "article", "id": AID, "headline": "H", "source": "S", "url": "u",
          "language": "en", "published_at": _dt(), "sortdate": _dt()}],
    ]))
    r = _client(app).get(f"/v1/entities/{EID}/coverage?pillar=articles")
    assert r.status_code == 200 and r.json()["meta"]["pillars"] == ["article"]


# ── articles ────────────────────────────────────────────────────────────────

def _article_row():
    return {"id": AID, "headline": "H", "summary": "s", "full_text": "f", "source": "S",
            "url": "u", "language": "en", "story_id": SID, "stance": "critical",
            "intensity": 0.8, "political_lean": "left", "low_credibility": False,
            "api_ready": True, "published_at": _dt(), "collected_at": _dt(),
            "last_updated": _dt(), "geo_primary": "IN"}


def test_list_articles_happy(app, monkeypatch):
    _override(app, _scope())
    monkeypatch.setattr(articles, "get_db", single_db([[_article_row()]]))
    r = _client(app).get("/v1/articles")
    assert r.status_code == 200 and r.json()["meta"]["count"] == 1


def test_list_articles_empty_scope(app):
    _override(app, _scope(entity_ids=()))
    r = _client(app).get("/v1/articles")
    assert r.status_code == 200 and r.json()["data"] == []


def test_get_article_happy(app, monkeypatch):
    _override(app, _scope())
    monkeypatch.setattr(articles, "get_db", single_db([
        [_article_row()],
        [{"id": EID, "name": "N", "type": "person"}],
    ]))
    r = _client(app).get(f"/v1/articles/{AID}")
    assert r.status_code == 200 and r.json()["data"]["id"] == AID


def test_get_article_bad_uuid(app):
    _override(app, _scope())
    assert _client(app).get("/v1/articles/bad").status_code == 404


def test_get_article_not_found(app, monkeypatch):
    _override(app, _scope())
    monkeypatch.setattr(articles, "get_db", single_db([[]]))
    assert _client(app).get(f"/v1/articles/{AID}").status_code == 404


# ── stories ─────────────────────────────────────────────────────────────────

def _story_row():
    return {"id": SID, "title": "T", "topic": "POL", "subject_country": "IN",
            "subject_region": "Karnataka", "event_type": "x", "article_count": 3,
            "outlets": 3, "languages": {"en": 2}, "importance_score": 0.9,
            "representative_article_id": AID, "first_seen_at": _dt(),
            "last_seen_at": _dt(), "top_outlets": ["A"]}


def test_list_stories_happy(app, monkeypatch):
    _override(app, _scope())
    monkeypatch.setattr(stories, "get_db", single_db([[_story_row()]]))
    r = _client(app).get("/v1/stories")
    assert r.status_code == 200 and r.json()["meta"]["count"] == 1


def test_list_stories_empty_scope(app):
    _override(app, _scope(entity_ids=(), regions=()))
    r = _client(app).get("/v1/stories")
    assert r.status_code == 200 and r.json()["data"] == []


def test_list_stories_with_entity_filter(app, monkeypatch):
    _override(app, _scope())
    monkeypatch.setattr(stories, "get_db", single_db([[_story_row()]]))
    r = _client(app).get(f"/v1/stories?entity={EID}")
    assert r.status_code == 200


def test_get_story_happy(app, monkeypatch):
    _override(app, _scope())
    monkeypatch.setattr(stories, "get_db", single_db([
        [_story_row()],
        [{"id": AID, "headline": "H", "source": "S", "url": "u", "language": "en",
          "published_at": _dt(), "is_representative": True}],
        [{"name": "A", "n": 3}],
    ]))
    r = _client(app).get(f"/v1/stories/{SID}")
    assert r.status_code == 200 and r.json()["data"]["id"] == SID


def test_get_story_bad_uuid(app):
    _override(app, _scope())
    assert _client(app).get("/v1/stories/bad").status_code == 404


def test_get_story_not_found(app, monkeypatch):
    _override(app, _scope())
    monkeypatch.setattr(stories, "get_db", single_db([[]]))
    assert _client(app).get(f"/v1/stories/{SID}").status_code == 404


# ── brief ───────────────────────────────────────────────────────────────────

def test_brief_endpoints(app, monkeypatch):
    _override(app, _scope())
    for path in ("/v1/brief/today", "/v1/brief/situation", "/v1/brief/daily?date=2026-06-30"):
        monkeypatch.setattr(brief, "get_db", single_db([[_story_row()]]))
        r = _client(app).get(path)
        assert r.status_code == 200, path
        assert "sections" in r.json()["data"]


# ── geo ─────────────────────────────────────────────────────────────────────

def test_geo_coverage_happy(app, monkeypatch):
    _override(app, _scope(regions=("Karnataka",)))
    monkeypatch.setattr(geo, "get_db", single_db([
        [{"state_code": "KA", "district_id": "d1", "district": "Blr", "n": 4}],
    ]))
    r = _client(app).get("/v1/geo/coverage")
    assert r.status_code == 200 and r.json()["data"]["states"][0]["articles"] == 4


def test_geo_coverage_empty_scope(app):
    _override(app, _scope(entity_ids=(), regions=()))
    r = _client(app).get("/v1/geo/coverage")
    assert r.status_code == 200 and r.json()["data"]["states"] == []


def test_geo_district_happy(app, monkeypatch):
    _override(app, _scope(regions=("Karnataka",)))
    monkeypatch.setattr(geo, "get_db", single_db([
        [{"id": "d1", "name": "Blr", "state_code": "KA", "hq_city": "Bengaluru"}],
        [{"n": 2, "sup": 1, "crit": 0, "neu": 1}],
        [],
    ]))
    r = _client(app).get("/v1/geo/district/d1")
    assert r.status_code == 200 and r.json()["data"]["state_code"] == "KA"


def test_geo_district_unknown(app, monkeypatch):
    _override(app, _scope())
    monkeypatch.setattr(geo, "get_db", single_db([[]]))
    assert _client(app).get("/v1/geo/district/nope").status_code == 404


def test_geo_district_out_of_scope(app, monkeypatch):
    _override(app, _scope(regions=("Telangana",)))  # TG scope, district is KA
    monkeypatch.setattr(geo, "get_db", single_db([
        [{"id": "d1", "name": "Blr", "state_code": "KA", "hq_city": "Bengaluru"}],
        [{"n": 0, "sup": 0, "crit": 0, "neu": 0}],
        [],
    ]))
    assert _client(app).get("/v1/geo/district/d1").status_code == 404


# ── analytics ───────────────────────────────────────────────────────────────

def test_analytics_topics(app, monkeypatch):
    _override(app, _scope())
    monkeypatch.setattr(analytics, "get_db", single_db([[{"name": "POL", "n": 5}]]))
    r = _client(app).get("/v1/analytics/topics")
    assert r.status_code == 200 and r.json()["data"]["topics"][0]["count"] == 5


def test_analytics_outlets(app, monkeypatch):
    _override(app, _scope())
    monkeypatch.setattr(analytics, "get_db", single_db([
        [{"id": EID, "name": "N", "type": "person"}],
        [{"name": "A", "n": 4, "sup": 2, "crit": 1, "neu": 1}],
    ]))
    r = _client(app).get(f"/v1/analytics/outlets?entity={EID}")
    assert r.status_code == 200 and r.json()["data"]["subject"] == "N"


def test_analytics_outlets_bad_entity(app):
    _override(app, _scope())
    assert _client(app).get("/v1/analytics/outlets?entity=bad").status_code == 400


def test_analytics_sentiment_by_id(app, monkeypatch):
    _override(app, _scope())
    monkeypatch.setattr(analytics, "get_db", single_db([
        [{"id": EID, "name": "N", "type": "person"}],
        [{"stance": "critical", "n": 2}],
        [{"day": datetime.date(2026, 6, 30), "sup": 0, "crit": 2, "neu": 0}],
    ]))
    r = _client(app).get(f"/v1/analytics/sentiment?entity={EID}")
    assert r.status_code == 200 and r.json()["data"]["subject"] == "N"


def test_analytics_sentiment_by_name(app, monkeypatch):
    _override(app, _scope(all_entities=True, entity_ids=()))
    monkeypatch.setattr(analytics, "get_db", single_db([
        [{"id": EID}],                                    # resolve_entity_by_name
        [{"id": EID, "name": "Modi", "type": "person"}],  # get_entity_row
        [{"stance": "supportive", "n": 3}],               # sentiment_split
        [],                                               # sentiment_daily
    ]))
    r = _client(app).get("/v1/analytics/sentiment?entity=Modi")
    assert r.status_code == 200 and r.json()["data"]["subject"] == "Modi"


def test_analytics_sentiment_name_not_found(app, monkeypatch):
    _override(app, _scope(all_entities=True, entity_ids=()))
    monkeypatch.setattr(analytics, "get_db", single_db([[]]))  # resolve -> None
    assert _client(app).get("/v1/analytics/sentiment?entity=Nobody").status_code == 404


def test_analytics_coverage(app, monkeypatch):
    _override(app, _scope())
    monkeypatch.setattr(analytics, "get_db",
                        single_db([[{"day": datetime.date(2026, 6, 30), "n": 3}]]))
    r = _client(app).get("/v1/analytics/coverage")
    assert r.status_code == 200 and r.json()["data"]["window_days"] == 7


# ── scope self-management ───────────────────────────────────────────────────

def test_read_scope(app):
    _override(app, _scope())
    r = _client(app).get("/v1/scope")
    assert r.status_code == 200 and r.json()["data"]["can_manage"] is True


def test_patch_scope_happy(app, monkeypatch):
    _override(app, _scope())
    monkeypatch.setattr(scope_ep, "get_db", single_db([[]]))
    r = _client(app).patch("/v1/scope", json={"add_entities": [EID2],
                                              "add_keywords": ["foo"],
                                              "keyword_priorities": {"foo": 3}})
    assert r.status_code == 200
    assert EID2 in r.json()["data"]["entity_ids"]


def test_patch_scope_forbidden(app):
    _override(app, _scope(can_manage=False), can_manage=False)
    assert _client(app).patch("/v1/scope", json={}).status_code == 403


def test_patch_scope_bad_entity(app):
    _override(app, _scope())
    r = _client(app).patch("/v1/scope", json={"add_entities": ["not-a-uuid"]})
    assert r.status_code == 400


def test_purge_scope_requires_confirm(app):
    _override(app, _scope())
    assert _client(app).post("/v1/scope/purge", json={"confirm": False}).status_code == 400


def test_purge_scope_happy(app, monkeypatch):
    _override(app, _scope())
    monkeypatch.setattr(scope_ep, "get_db", single_db([[]]))
    r = _client(app).post("/v1/scope/purge", json={"confirm": True})
    assert r.status_code == 200 and r.json()["data"]["purged"] is True


# ── usage ───────────────────────────────────────────────────────────────────

def test_usage(app, monkeypatch):
    _override(app, _scope())
    monkeypatch.setattr(usage, "get_db", single_db([
        [{"request_count": 42}],
        [{"endpoint": "/v1/articles", "n": 40}],
    ]))
    r = _client(app).get("/v1/usage")
    assert r.status_code == 200 and r.json()["data"]["requests"] == 42


# ── webhooks ────────────────────────────────────────────────────────────────

def test_create_webhook_happy(app, monkeypatch):
    _override(app, _scope())
    monkeypatch.setattr(webhooks, "get_db", single_db([
        [{"n": 0}],                            # count
        [{"id": "w1", "is_active": True}],     # insert returning
    ]))
    import v1.webhook_delivery as wd
    monkeypatch.setattr(wd, "_ssrf_ok", lambda url: True)
    r = _client(app).post("/v1/webhooks", json={"url": "https://ok.example",
                                               "filter": {"topic": "POL", "bad": "x"}})
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["secret"].startswith("whsec_") and body["filter"] == {"topic": "POL"}


def test_create_webhook_not_https(app):
    _override(app, _scope())
    assert _client(app).post("/v1/webhooks", json={"url": "http://x"}).status_code == 400


def test_create_webhook_ssrf_blocked(app, monkeypatch):
    _override(app, _scope())
    import v1.webhook_delivery as wd
    monkeypatch.setattr(wd, "_ssrf_ok", lambda url: False)
    r = _client(app).post("/v1/webhooks", json={"url": "https://169.254.169.254"})
    assert r.status_code == 400


def test_create_webhook_limit(app, monkeypatch):
    _override(app, _scope())
    import v1.webhook_delivery as wd
    monkeypatch.setattr(wd, "_ssrf_ok", lambda url: True)
    monkeypatch.setattr(webhooks, "get_db", single_db([[{"n": 25}]]))
    r = _client(app).post("/v1/webhooks", json={"url": "https://ok.example"})
    assert r.status_code == 400


def test_list_webhooks(app, monkeypatch):
    _override(app, _scope())
    monkeypatch.setattr(webhooks, "get_db", single_db([
        [{"id": "w1", "url": "https://x", "filter": {}, "is_active": True,
          "created_at": _dt(), "last_delivered_at": None}],
    ]))
    r = _client(app).get("/v1/webhooks")
    assert r.status_code == 200 and r.json()["meta"]["count"] == 1


def test_delete_webhook_happy(app, monkeypatch):
    _override(app, _scope())
    monkeypatch.setattr(webhooks, "get_db", single_db([[{"x": 1}]]))  # rowcount 1
    r = _client(app).delete(f"/v1/webhooks/{AID}")
    assert r.status_code == 200 and r.json()["data"]["deleted"] is True


def test_delete_webhook_bad_uuid(app):
    _override(app, _scope())
    assert _client(app).delete("/v1/webhooks/bad").status_code == 404


def test_delete_webhook_not_found(app, monkeypatch):
    _override(app, _scope())
    monkeypatch.setattr(webhooks, "get_db", single_db([[]]))  # rowcount 0
    assert _client(app).delete(f"/v1/webhooks/{AID}").status_code == 404


# ── health ──────────────────────────────────────────────────────────────────

def test_health(app):
    r = _client(app).get("/v1/health")
    assert r.status_code == 200 and r.json()["data"]["status"] == "ok"
