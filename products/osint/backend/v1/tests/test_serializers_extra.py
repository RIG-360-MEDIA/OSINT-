"""Branch coverage for serializers.py, util.py, settings.py, keys.prefix_of."""
from __future__ import annotations

import datetime

from _fakes import FakeSession  # noqa: F401,E402  (ensures env is set)

from v1 import serializers as S  # noqa: E402
from v1 import settings, util  # noqa: E402


def _dt():
    return datetime.datetime(2026, 6, 30, 12, 0, tzinfo=datetime.timezone.utc)


# ── serializers helpers ─────────────────────────────────────────────────────

def test_iso_and_clip_and_as_float():
    assert S._iso(None) is None
    assert S._iso(_dt()) == _dt().isoformat()
    assert S._iso("not-a-date") is None
    assert S._clip(None) is None
    assert S._clip("") is None
    assert S._clip("short") == "short"
    # Relative to the constant, not a literal: the ceiling moved 400 -> 2000 on
    # 2026-07-17 and a hard-coded bound silently tests the wrong thing.
    assert S._clip("x" * (S._SUMMARY_MAX - 1)) == "x" * (S._SUMMARY_MAX - 1)
    long = "x" * (S._SUMMARY_MAX + 100)
    assert len(S._clip(long)) == S._SUMMARY_MAX and S._clip(long).endswith("…")
    assert S._as_float(None) is None
    assert S._as_float("nan-ish") is None
    assert S._as_float("1.23456") == 1.235
    assert S._as_float(2) == 2.0


def test_stance_label():
    assert S._stance_label("positive") == "supportive"
    assert S._stance_label("NEGATIVE") == "critical"
    assert S._stance_label("neutral") == "neutral"
    assert S._stance_label("weird") is None
    assert S._stance_label(None) is None


def test_source_flags():
    assert S._source_flags({"low_credibility": True})["low_credibility"] is True
    f = S._source_flags({"political_lean": "left"})
    assert f["political_lean"] == "left"
    # 'unknown'/empty leans are dropped
    assert "political_lean" not in S._source_flags({"political_lean": "unknown"})
    assert "political_lean" not in S._source_flags({"political_lean": ""})


def test_serialize_article_with_sentiment_and_entities():
    row = {"id": "a", "headline": "H", "stance": "critical", "intensity": 0.7,
           "political_lean": "left", "low_credibility": True, "api_ready": True,
           "story_id": "s1", "geo_primary": "IN", "full_text": "body"}
    out = S.serialize_article(row, entities=[{"id": "e", "name": "N", "type": "person"}])
    assert out["sentiment"] == {"label": "critical", "intensity": 0.7}
    assert out["story_id"] == "s1" and out["full_text"] == "body"
    assert out["entities"] == [{"id": "e", "name": "N", "type": "person"}]
    assert out["source_flags"]["political_lean"] == "left"


def test_serialize_story_and_detail_and_outlets():
    row = {"id": "s", "title": "T", "topic": "POL", "subject_country": "IN",
           "subject_region": "TG", "event_type": "protest", "article_count": 3,
           "outlets": 2, "top_outlets": ["A"], "languages": {"en": 2},
           "importance_score": 0.5, "representative_article_id": "r",
           "first_seen_at": _dt(), "last_seen_at": _dt()}
    st = S.serialize_story(row)
    assert st["languages"] == {"en": 2} and st["importance"] == 0.5
    # languages non-dict -> None; event_type falsy -> None; top_outlets missing -> []
    st2 = S.serialize_story({"languages": "en", "event_type": "", "top_outlets": None})
    assert st2["languages"] is None and st2["event_type"] is None and st2["top_outlets"] == []
    detail = S.serialize_story_detail({
        "story": row,
        "outlets": [{"name": "A", "count": 3}],
        "timeline": [{"id": "t", "headline": "H", "source": "S", "url": "u",
                      "language": "en", "is_representative": True, "published_at": _dt()}],
    })
    assert detail["outlets_breakdown"] == [{"name": "A", "count": 3}]
    assert detail["timeline"][0]["is_representative"] is True
    o = S.serialize_outlets("Subj", [{"name": "A", "count": 2, "net_lean": 0.1}], 7)
    assert o["subject"] == "Subj" and o["outlets"][0]["net_lean"] == 0.1 and "basis" in o


def test_serialize_coverage_item_and_sentiment_daily():
    ci = S.serialize_coverage_item({"type": "clip", "id": "c", "headline": "H",
                                    "source": "yt", "language": "en", "url": "u",
                                    "published_at": _dt()})
    assert ci["type"] == "clip" and ci["published_at"] == _dt().isoformat()
    sent = S.serialize_sentiment({"total": 2, "supportive": 1, "neutral": 0, "critical": 1,
                                  "net_lean": 0.0}, "X", 7, daily=[{"date": "2026-06-30"}])
    assert sent["daily"] == [{"date": "2026-06-30"}]


# ── util.as_uuid ────────────────────────────────────────────────────────────

def test_as_uuid():
    good = "11111111-1111-1111-1111-111111111111"
    assert util.as_uuid(good) == good
    assert util.as_uuid("  " + good + "  ") == good
    assert util.as_uuid("not-a-uuid") is None
    assert util.as_uuid(123) is None
    assert util.as_uuid(None) is None


# ── settings.hash_secret ────────────────────────────────────────────────────

def test_hash_secret_returns_configured():
    # env has OSINT_APIKEY_HASH_SECRET set (via _fakes) -> returns it, cached.
    assert settings.hash_secret() == settings.hash_secret()
    assert isinstance(settings.hash_secret(), str) and settings.hash_secret()


def test_hash_secret_dev_fallback(monkeypatch):
    # Force the "no configured secret, development" path -> dev fallback.
    monkeypatch.setattr(settings, "_cached_secret", None)
    monkeypatch.setattr(settings, "_HASH_SECRET", "")
    monkeypatch.setattr(settings, "_HASH_SECRET_FILE", "/nonexistent/secret/file")
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    assert settings.hash_secret() == settings._DEV_FALLBACK_SECRET
    monkeypatch.setattr(settings, "_cached_secret", None)


def test_hash_secret_prod_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "_cached_secret", None)
    monkeypatch.setattr(settings, "_HASH_SECRET", "")
    monkeypatch.setattr(settings, "_HASH_SECRET_FILE", "/nonexistent/secret/file")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    try:
        settings.hash_secret()
        assert False, "prod must fail closed"
    except RuntimeError:
        pass
    monkeypatch.setattr(settings, "_cached_secret", None)
