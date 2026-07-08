"""No-DB coverage for queries.py — every function driven with a FakeSession.

Each query takes ``db`` as a parameter and only awaits ``db.execute``; we feed
canned rows and assert the built shape, exercising both branches of each
conditional so the clause-building lines all run.
"""
from __future__ import annotations

import asyncio
import datetime

from _fakes import FakeSession  # noqa: E402

from v1 import queries  # noqa: E402
from v1.errors import GatewayError  # noqa: E402
from v1.pagination import encode_cursor  # noqa: E402

UUID = "11111111-1111-1111-1111-111111111111"
UUID2 = "22222222-2222-2222-2222-222222222222"


def run(coro):
    return asyncio.run(coro)


def _dt(day=30):
    return datetime.datetime(2026, 6, day, 12, 0, tzinfo=datetime.timezone.utc)


def _date(day=30):
    return datetime.date(2026, 6, day)


# ── list_scoped_entities ────────────────────────────────────────────────────

def test_list_scoped_entities_all():
    rows = [{"id": UUID, "name": "N", "type": "person"}]
    out = run(queries.list_scoped_entities(FakeSession([rows]), [], True, 500))
    assert out == [{"id": UUID, "name": "N", "type": "person"}]


def test_list_scoped_entities_by_ids():
    rows = [{"id": UUID, "name": "N", "type": "org"}]
    out = run(queries.list_scoped_entities(FakeSession([rows]), [UUID], False, 500))
    assert out[0]["type"] == "org"


def test_list_scoped_entities_empty_scope():
    assert run(queries.list_scoped_entities(FakeSession([]), [], False, 500)) == []


# ── get_entity_row / resolve_entity_by_name ─────────────────────────────────

def test_get_entity_row_hit_and_miss():
    hit = run(queries.get_entity_row(FakeSession([[{"id": UUID, "name": "N", "type": "person"}]]), UUID))
    assert hit["id"] == UUID
    assert run(queries.get_entity_row(FakeSession([[]]), UUID)) is None


def test_resolve_entity_by_name_branches():
    # all_entities
    assert run(queries.resolve_entity_by_name(FakeSession([[{"id": UUID}]]), "n", [], True)) == UUID
    # scoped ids
    assert run(queries.resolve_entity_by_name(FakeSession([[{"id": UUID2}]]), "n", [UUID2], False)) == UUID2
    # empty scope -> None (no db touch)
    assert run(queries.resolve_entity_by_name(FakeSession([]), "n", [], False)) is None
    # not found
    assert run(queries.resolve_entity_by_name(FakeSession([[]]), "n", [], True)) is None


# ── entity_coverage_count ───────────────────────────────────────────────────

def test_entity_coverage_count():
    assert run(queries.entity_coverage_count(FakeSession([[{"n": 7}]]), UUID, 168)) == 7
    assert run(queries.entity_coverage_count(FakeSession([[]]), UUID, 168)) == 0


# ── sentiment_split / sentiment_daily ───────────────────────────────────────

def test_sentiment_split_aggregates_all_labels():
    rows = [{"stance": "supportive", "n": 3}, {"stance": "positive", "n": 1},
            {"stance": "critical", "n": 2}, {"stance": "negative", "n": 1},
            {"stance": "neutral", "n": 4}, {"stance": "garbage", "n": 9}]
    out = run(queries.sentiment_split(FakeSession([rows]), UUID, 168))
    assert out["supportive"] == 4 and out["critical"] == 3 and out["neutral"] == 4
    assert out["total"] == 11
    assert out["net_lean"] == round((4 - 3) / 11, 4)


def test_sentiment_split_empty_net_lean_zero():
    out = run(queries.sentiment_split(FakeSession([[]]), UUID, 168))
    assert out["total"] == 0 and out["net_lean"] == 0.0


def test_sentiment_daily():
    rows = [{"day": _date(29), "sup": 2, "crit": 1, "neu": 0},
            {"day": _date(30), "sup": 0, "crit": 0, "neu": 3}]
    out = run(queries.sentiment_daily(FakeSession([rows]), UUID, 168))
    assert out[0]["date"] == "2026-06-29" and out[0]["supportive"] == 2
    assert out[1]["neutral"] == 3


# ── coverage_daily ──────────────────────────────────────────────────────────

def test_coverage_daily_scoped_and_all():
    rows = [{"day": _date(29), "n": 5}, {"day": _date(30), "n": 2}]
    scoped = run(queries.coverage_daily(FakeSession([rows]), [UUID], False, 168))
    assert scoped["total"] == 7 and len(scoped["daily"]) == 2
    alle = run(queries.coverage_daily(FakeSession([rows]), [], True, 168))
    assert alle["total"] == 7


def test_coverage_daily_empty_scope():
    out = run(queries.coverage_daily(FakeSession([]), [], False, 168))
    assert out == {"total": 0, "daily": []}


# ── topics_breakdown ────────────────────────────────────────────────────────

def test_topics_breakdown_branches():
    rows = [{"name": "POLITICS", "n": 9}, {"name": "SPORTS", "n": 4}]
    scoped = run(queries.topics_breakdown(FakeSession([rows]), [UUID], False, 168, 10))
    assert scoped[0] == {"name": "POLITICS", "count": 9}
    alle = run(queries.topics_breakdown(FakeSession([rows]), [], True, 168, 10))
    assert len(alle) == 2
    assert run(queries.topics_breakdown(FakeSession([]), [], False, 168, 10)) == []


# ── outlets_for_entity ──────────────────────────────────────────────────────

def test_outlets_for_entity_net_lean():
    rows = [{"name": "Outlet A", "n": 10, "sup": 3, "crit": 1, "neu": 2},
            {"name": "Outlet B", "n": 2, "sup": 0, "crit": 0, "neu": 0}]
    out = run(queries.outlets_for_entity(FakeSession([rows]), UUID, 168, 20))
    assert out[0]["net_lean"] == round((3 - 1) / 6, 4)
    assert out[1]["net_lean"] == 0.0  # zero classified -> 0.0


# ── list_scoped_articles ────────────────────────────────────────────────────

def _article_row(day=30):
    return {
        "id": UUID, "headline": "H", "summary": "s", "full_text": "f", "source": "Src",
        "url": "https://x", "language": "en", "story_id": UUID2, "stance": "critical",
        "intensity": 0.8, "political_lean": "left", "low_credibility": False,
        "api_ready": True, "published_at": _dt(day), "collected_at": _dt(day),
        "last_updated": _dt(day), "geo_primary": "IN",
    }


def test_list_scoped_articles_empty_scope():
    rows, cur = run(queries.list_scoped_articles(
        FakeSession([]), entity_ids=[], all_entities=False, window_hours=168,
        language=None, sentiment=None, cursor=None, limit=20))
    assert rows == [] and cur is None


def test_list_scoped_articles_all_filters_and_cursor():
    # limit=1 with 1 row -> next_cursor produced
    cursor = encode_cursor(_dt(30), UUID)
    rows, nxt = run(queries.list_scoped_articles(
        FakeSession([[_article_row()]]),
        entity_ids=[UUID], all_entities=False, window_hours=168,
        language="en", sentiment="critical", cursor=cursor, limit=1,
        mute_terms=("bad", "worse")))
    assert rows[0]["id"] == UUID
    assert nxt is not None  # len(rows)==limit -> cursor emitted


def test_list_scoped_articles_all_entities_sentiment_branch():
    rows, nxt = run(queries.list_scoped_articles(
        FakeSession([[_article_row()]]),
        entity_ids=[], all_entities=True, window_hours=168,
        language=None, sentiment="supportive", cursor=None, limit=20))
    assert rows and nxt is None  # fewer than limit -> no cursor


# ── get_scoped_article ──────────────────────────────────────────────────────

def test_get_scoped_article_branches():
    row = _article_row()
    row.pop("collected_at", None)  # detail query has no collected_at
    hit = run(queries.get_scoped_article(FakeSession([[row]]), UUID, [UUID], False))
    assert hit["id"] == UUID
    # all_entities path
    hit2 = run(queries.get_scoped_article(FakeSession([[row]]), UUID, [], True))
    assert hit2["id"] == UUID
    # empty scope, not all_entities -> None without db
    assert run(queries.get_scoped_article(FakeSession([]), UUID, [], False)) is None
    # miss
    assert run(queries.get_scoped_article(FakeSession([[]]), UUID, [UUID], False)) is None


# ── article_entities ────────────────────────────────────────────────────────

def test_article_entities_branches():
    rows = [{"id": UUID, "name": "N", "type": "person"}]
    assert run(queries.article_entities(FakeSession([rows]), UUID, [], True))[0]["id"] == UUID
    assert run(queries.article_entities(FakeSession([rows]), UUID, [UUID], False))[0]["name"] == "N"
    assert run(queries.article_entities(FakeSession([]), UUID, [], False)) == []


# ── list_scoped_stories ─────────────────────────────────────────────────────

def _story_row():
    return {
        "id": UUID, "title": "T", "topic": "POLITICS", "subject_country": "IN",
        "subject_region": "Telangana", "event_type": "protest", "article_count": 12,
        "outlets": 5, "languages": {"en": 3}, "importance_score": 0.9,
        "representative_article_id": UUID2, "first_seen_at": _dt(29),
        "last_seen_at": _dt(30), "top_outlets": ["A", "B"],
    }


def test_list_scoped_stories_empty_scope():
    rows, cur = run(queries.list_scoped_stories(
        FakeSession([]), entity_ids=[], all_entities=False, regions=(),
        country=None, cursor=None, limit=20))
    assert rows == [] and cur is None


def test_list_scoped_stories_entity_and_region_scope_with_cursor():
    cur_in = encode_cursor(0.9, UUID)
    rows, nxt = run(queries.list_scoped_stories(
        FakeSession([[_story_row()]]),
        entity_ids=[UUID], all_entities=False, regions=("Telangana",),
        country="IN", cursor=cur_in, limit=1, mute_terms=("mute",)))
    assert rows[0]["id"] == UUID and nxt is not None


def test_list_scoped_stories_all_entities():
    rows, nxt = run(queries.list_scoped_stories(
        FakeSession([[_story_row()]]),
        entity_ids=[], all_entities=True, regions=(), country=None,
        cursor=None, limit=20))
    assert rows and nxt is None


def test_list_scoped_stories_bad_cursor():
    try:
        run(queries.list_scoped_stories(
            FakeSession([[_story_row()]]),
            entity_ids=[], all_entities=True, regions=(), country=None,
            cursor=encode_cursor("not-a-float", UUID), limit=20))
        assert False, "expected bad cursor"
    except GatewayError as e:
        assert e.status == 400


# ── story_detail ────────────────────────────────────────────────────────────

def test_story_detail_full():
    story = _story_row()
    timeline = [{"id": UUID, "headline": "H", "source": "S", "url": "u",
                 "language": "en", "published_at": _dt(30), "is_representative": True}]
    outlets = [{"name": "A", "n": 3}]
    data = run(queries.story_detail(
        FakeSession([[story], timeline, outlets]),
        story_id=UUID, entity_ids=[UUID], all_entities=False,
        regions=("Telangana",), limit=60))
    assert data["story"]["id"] == UUID
    assert data["timeline"][0]["is_representative"] is True
    assert data["outlets"][0] == {"name": "A", "count": 3}


def test_story_detail_all_entities_and_miss():
    story = _story_row()
    data = run(queries.story_detail(
        FakeSession([[story], [], []]),
        story_id=UUID, entity_ids=[], all_entities=True, regions=(), limit=60))
    assert data["story"]["id"] == UUID
    # empty scope -> None before db
    assert run(queries.story_detail(
        FakeSession([]), story_id=UUID, entity_ids=[], all_entities=False,
        regions=(), limit=60)) is None
    # story not found
    assert run(queries.story_detail(
        FakeSession([[]]), story_id=UUID, entity_ids=[], all_entities=True,
        regions=(), limit=60)) is None


# ── geo_coverage ────────────────────────────────────────────────────────────

def test_geo_coverage_groups_by_state():
    rows = [{"state_code": "TG", "district_id": "d1", "district": "Hyd", "n": 5},
            {"state_code": "TG", "district_id": "d2", "district": "Warangal", "n": 2},
            {"state_code": "AP", "district_id": "d3", "district": "Vizag", "n": 1}]
    out = run(queries.geo_coverage(
        FakeSession([rows]), entity_ids=[UUID], all_entities=False,
        state_codes=["TG"], window_hours=168))
    tg = [s for s in out if s["state_code"] == "TG"][0]
    assert tg["articles"] == 7 and len(tg["districts"]) == 2


def test_geo_coverage_all_entities_and_empty_scope():
    rows = [{"state_code": "TG", "district_id": "d1", "district": "Hyd", "n": 5}]
    alle = run(queries.geo_coverage(
        FakeSession([rows]), entity_ids=[], all_entities=True,
        state_codes=[], window_hours=168))
    assert alle[0]["articles"] == 5
    # no entities, no state codes, not all -> [] before db
    assert run(queries.geo_coverage(
        FakeSession([]), entity_ids=[], all_entities=False,
        state_codes=[], window_hours=168)) == []


# ── geo_district ────────────────────────────────────────────────────────────

def test_geo_district_full_and_miss():
    meta = [{"id": "d1", "name": "Hyd", "state_code": "TG", "hq_city": "Hyderabad"}]
    stats = [{"n": 4, "sup": 2, "crit": 1, "neu": 1}]
    recent = [{"id": UUID, "headline": "H", "source": "S", "url": "u",
               "language": "en", "published_at": _dt(30)}]
    out = run(queries.geo_district(FakeSession([meta, stats, recent]), "d1", 168, 20))
    assert out["articles"] == 4 and out["stance"]["supportive"] == 2
    assert out["recent"][0]["published_at"] == _dt(30).isoformat()
    # unknown slug
    assert run(queries.geo_district(FakeSession([[]]), "nope", 168, 20)) is None


def test_geo_district_null_published_at():
    meta = [{"id": "d1", "name": "Hyd", "state_code": "TG", "hq_city": "Hyderabad"}]
    stats = [{"n": 0, "sup": None, "crit": None, "neu": None}]
    recent = [{"id": UUID, "headline": "H", "source": "S", "url": "u",
               "language": "en", "published_at": None}]
    out = run(queries.geo_district(FakeSession([meta, stats, recent]), "d1", 168, 20))
    assert out["recent"][0]["published_at"] is None
    assert out["stance"]["supportive"] == 0


# ── entity_multi_coverage ───────────────────────────────────────────────────

def test_entity_multi_coverage_all_pillars_with_lang():
    rows = [{"type": "article", "id": UUID, "headline": "H", "source": "S",
             "url": "u", "language": "en", "published_at": _dt(30), "sortdate": _dt(30)}]
    out = run(queries.entity_multi_coverage(
        FakeSession([rows]), entity_id=UUID, window_hours=168, language="en",
        pillars=["article", "clip", "cutting"], limit=20))
    assert out[0]["type"] == "article"


def test_entity_multi_coverage_no_pillars_and_no_lang():
    assert run(queries.entity_multi_coverage(
        FakeSession([]), entity_id=UUID, window_hours=168, language=None,
        pillars=[], limit=20)) == []
    rows = [{"type": "clip", "id": UUID, "headline": "H", "source": "S",
             "url": "u", "language": "en", "published_at": _dt(30), "sortdate": _dt(30)}]
    out = run(queries.entity_multi_coverage(
        FakeSession([rows]), entity_id=UUID, window_hours=168, language=None,
        pillars=["clip"], limit=20))
    assert out[0]["type"] == "clip"
