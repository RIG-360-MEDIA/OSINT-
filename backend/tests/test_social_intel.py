"""
Tests for the Signal Room intel layer.

Covers:
  - _compute_relevance pure-function correctness (8 signal weights)
  - render_summary template smoke (composes a typewriter document)
  - codename helper (TG-* / R/* mapping)
  - dtg helper (date-time-group format)
  - /api/signals/summary/latest endpoint shape
  - /api/signals/summary/editions endpoint shape
  - /api/signals/topic/{kind}/{key} endpoint shape (entity / cluster / subject)
  - /api/signals/seeds endpoint
"""
from __future__ import annotations

import re
import types
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth.auth_middleware import get_current_user
from backend.routers import signals_router as signals_module
from backend.routers.signals_router import signals_router
from backend.tasks.social_intel_task import (
    _auto_promote_subjects,
    _codename,
    _dtg,
    _recompute_baselines,
    _render_summary,
)
from backend.tasks.social_task import _compute_relevance


TEST_USER_ID = "11111111-1111-1111-1111-111111111111"


# ── Fake DB plumbing (mirror of test_signals_router) ───────────────────────


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
    def __init__(self, responses: list[list[FakeRow]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def execute(
        self, query: Any, params: dict[str, Any] | None = None
    ) -> FakeResult:
        self.calls.append((str(query), dict(params or {})))
        if not self.responses:
            return FakeResult([])
        return FakeResult(self.responses.pop(0))

    async def commit(self) -> None:  # pragma: no cover
        return None


def install_fake_db(
    monkeypatch: pytest.MonkeyPatch, session: FakeSession
) -> None:
    @asynccontextmanager
    async def fake_get_db():
        yield session

    monkeypatch.setattr(signals_module, "get_db", fake_get_db)


def make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(signals_router)
    app.dependency_overrides[get_current_user] = lambda: {
        "id": TEST_USER_ID,
        "email": "t@x",
    }
    return app


# ── _compute_relevance ─────────────────────────────────────────────────────


@pytest.mark.unit
def test_relevance_zero_for_empty_text() -> None:
    assert (
        _compute_relevance("", [], 0.0, False, [], []) == 0
    )


@pytest.mark.unit
def test_relevance_entity_match_25() -> None:
    s = _compute_relevance(
        "BRS announces new policy",
        ["BRS"],
        0.0,
        False,
        [],
        [],
    )
    assert s == 25


@pytest.mark.unit
def test_relevance_official_monitor_20() -> None:
    s = _compute_relevance(
        "Routine ministry update",
        [],
        0.0,
        True,
        [],
        [],
    )
    assert s == 20


@pytest.mark.unit
def test_relevance_geo_seed_15() -> None:
    s = _compute_relevance(
        "Local news from Hyderabad municipality",
        [],
        0.0,
        False,
        ["Hyderabad"],
        [],
    )
    assert s == 15


@pytest.mark.unit
def test_relevance_topic_seed_15() -> None:
    s = _compute_relevance(
        "Massive protest in central square today",
        [],
        0.0,
        False,
        [],
        ["protest"],
    )
    assert s == 15


@pytest.mark.unit
def test_relevance_sentiment_extremity_5() -> None:
    s = _compute_relevance(
        "ordinary text",
        [],
        -0.7,
        False,
        [],
        [],
    )
    assert s == 5


@pytest.mark.unit
def test_relevance_full_stack_clamped() -> None:
    """All signals stack but cap at 100."""
    s = _compute_relevance(
        "BRS announces protest in Hyderabad",
        ["BRS"],
        0.6,
        True,
        ["Hyderabad"],
        ["protest"],
    )
    # 25 + 20 + 15 + 15 + 5 = 80
    assert s == 80


@pytest.mark.unit
def test_relevance_cap_at_100() -> None:
    """Manual stress: contrived to exceed 100 cap."""
    # Re-call with multiple matches using the same haystack
    # The function's max possible from current weights is 80; ensure
    # the cap clause doesn't accidentally undershoot.
    s = _compute_relevance(
        "X" * 200,
        ["X"],
        1.0,
        True,
        ["X"],
        ["X"],
    )
    assert s <= 100


@pytest.mark.unit
def test_relevance_case_insensitive_seeds() -> None:
    s = _compute_relevance(
        "newsflash from HYDERABAD",
        [],
        0.0,
        False,
        ["hyderabad"],
        [],
    )
    assert s == 15


# ── _codename ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_codename_reddit_passthrough() -> None:
    assert _codename("r/india") == "R/INDIA"
    assert _codename("R/India") == "R/INDIA"


@pytest.mark.unit
def test_codename_telegram_strips_punct_and_uppercases() -> None:
    assert _codename("MIB_India", "telegram") == "TG-MIBINDIA"
    assert _codename("scroll.in", "telegram") == "TG-SCROLLIN"
    assert _codename("BJP4India", "telegram") == "TG-BJP4INDIA"


@pytest.mark.unit
def test_codename_reddit_with_hint() -> None:
    assert _codename("Andhrapradesh", "reddit") == "R/ANDHRAPRADESH"


@pytest.mark.unit
def test_codename_unknown_handles_empty() -> None:
    # No platform hint + empty identifier → just "?"
    assert _codename("") == "?"


# ── _dtg ───────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_dtg_format() -> None:
    out = _dtg()
    # 271423Z APR 26 — six digits, Z, three-letter month, two-digit year
    assert re.fullmatch(r"\d{6}Z [A-Z]{3} \d{2}", out)


# ── _render_summary ────────────────────────────────────────────────────────


def _evt(
    event_type: str = "SURGE",
    subject: str = "BRS",
    confidence: str = "HIGH",
    body: str = "BRS mentions at 3.0× baseline.",
    metadata: dict[str, Any] | None = None,
    sources: list[str] | None = None,
) -> FakeRow:
    return FakeRow(
        id=uuid4(),
        event_type=event_type,
        subject=subject,
        subject_kind="entity" if event_type != "REPETITION" else "cluster",
        magnitude=3.0,
        confidence=confidence,
        sources=sources or ["r/india"],
        body=body,
        metadata=metadata or {"posts_24h": 12, "baseline": 4.0},
        detected_at=datetime.now(timezone.utc),
    )


@pytest.mark.unit
def test_render_summary_with_events() -> None:
    body = _render_summary(
        edition=4,
        events=[
            _evt("SURGE", "BRS"),
            _evt(
                "SENTIMENT_SHIFT",
                "Telangana High Court",
                metadata={"delta": -0.42, "from": 0.0, "to": -0.42},
            ),
            _evt(
                "REPETITION",
                str(uuid4()),
                body="MIB-Central repeated 4× in 36h.",
            ),
            _evt(
                "BRIDGE",
                str(uuid4()),
                body="Story crossed REDDIT → TELEGRAM after 45 min.",
            ),
            _evt(
                "SILENCE",
                "water shortage",
                body="grassroots surge unanswered by official channels",
            ),
            _evt(
                "NEW_SUBJECT",
                "Hyderabad metro Phase 2",
                metadata={"occurrences": 6, "source_count": 3},
            ),
        ],
        stationary=["KCR", "Bhatti"],
        sources_used=["R/INDIA", "TG-MIBINDIA"],
    )
    assert "DAILY SIGNAL SUMMARY" in body
    assert "EDITION 004" in body
    assert "ENTITIES UNDER SURGE" in body
    assert "BRS" in body
    assert "PHRASING REPETITION" in body
    assert "BRIDGE" in body
    assert "OFFICIAL SILENCE" in body
    assert "NEW ON THE RADAR" in body
    assert "STATIONARY" in body
    assert "— END —" in body


@pytest.mark.unit
def test_render_summary_empty_falls_back_to_nil() -> None:
    body = _render_summary(
        edition=1,
        events=[],
        stationary=[],
        sources_used=[],
    )
    assert "NIL" in body or "No detected signals" in body


# ── /summary/latest ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_summary_latest_requires_auth() -> None:
    app = FastAPI()
    app.include_router(signals_router)
    client = TestClient(app)
    assert client.get("/api/signals/summary/latest").status_code == 401


@pytest.mark.unit
def test_summary_latest_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_db(monkeypatch, FakeSession(responses=[[]]))
    body = TestClient(make_app()).get("/api/signals/summary/latest").json()
    assert body == {"summary": None}


@pytest.mark.unit
def test_summary_latest_returns_body(monkeypatch: pytest.MonkeyPatch) -> None:
    row = FakeRow(
        id=str(uuid4()),
        edition=7,
        classification="OPEN",
        generated_at=datetime.now(timezone.utc),
        window_hours=24,
        body="DAILY SIGNAL SUMMARY ...",
        sources_used=["R/INDIA"],
        event_ids=[uuid4(), uuid4()],
    )
    install_fake_db(monkeypatch, FakeSession(responses=[[row]]))
    body = TestClient(make_app()).get("/api/signals/summary/latest").json()
    assert body["summary"]["edition"] == 7
    assert body["summary"]["event_count"] == 2
    assert body["summary"]["body"].startswith("DAILY")


# ── /summary/editions ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_editions_requires_auth() -> None:
    app = FastAPI()
    app.include_router(signals_router)
    assert (
        TestClient(app).get("/api/signals/summary/editions").status_code
        == 401
    )


@pytest.mark.unit
def test_editions_returns_list(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        FakeRow(
            id=str(uuid4()),
            edition=i,
            classification="OPEN",
            generated_at=datetime.now(timezone.utc) - timedelta(hours=i * 6),
            window_hours=24,
        )
        for i in range(3)
    ]
    install_fake_db(monkeypatch, FakeSession(responses=[rows]))
    body = TestClient(make_app()).get("/api/signals/summary/editions").json()
    assert len(body["editions"]) == 3


# ── /topic/{kind}/{key} ────────────────────────────────────────────────────


def _topic_post_row(text: str = "Default text") -> FakeRow:
    now = datetime.now(timezone.utc)
    return FakeRow(
        post_id=str(uuid4()),
        platform="reddit",
        author_username="someone",
        post_text=text,
        post_text_translated=None,
        post_language="en",
        post_url="https://x.example/p",
        upvotes=10,
        comment_count=2,
        share_count=0,
        forward_count=0,
        forwarded_from=None,
        has_document=False,
        sentiment_score=0.1,
        matched_entities=["BRS"],
        relevance_score=45,
        posted_at=now - timedelta(minutes=10),
        collected_at=now - timedelta(minutes=5),
        monitor_name="r/india",
    )


@pytest.mark.unit
def test_topic_requires_auth() -> None:
    app = FastAPI()
    app.include_router(signals_router)
    assert (
        TestClient(app).get("/api/signals/topic/entity/BRS").status_code
        == 401
    )


@pytest.mark.unit
@pytest.mark.parametrize("kind", ["entity", "cluster", "subject"])
def test_topic_kinds_succeed(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    install_fake_db(
        monkeypatch,
        FakeSession(responses=[[_topic_post_row("Hello BRS")]]),
    )
    key = str(uuid4()) if kind == "cluster" else "BRS"
    body = TestClient(make_app()).get(
        f"/api/signals/topic/{kind}/{key}"
    ).json()
    assert body["kind"] == kind
    assert len(body["posts"]) == 1
    assert body["posts"][0]["relevance_score"] == 45


@pytest.mark.unit
def test_topic_invalid_kind_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_db(monkeypatch, FakeSession(responses=[]))
    body = TestClient(make_app()).get("/api/signals/topic/bogus/x").json()
    assert body["error"] == "invalid kind"


# ── /seeds ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_seeds_requires_auth() -> None:
    app = FastAPI()
    app.include_router(signals_router)
    assert TestClient(app).get("/api/signals/seeds").status_code == 401


# ── Auto-promote NEW_SUBJECT → user_entities ─────────────────────────────


class _PromoteSession:
    """FakeSession variant that tracks INSERT RETURNING semantics."""

    def __init__(
        self,
        owner_user_id: str | None,
        candidates: list[FakeRow],
        already_in: set[str] | None = None,
    ) -> None:
        self.owner_user_id = owner_user_id
        self.candidates = list(candidates)
        self.already_in = already_in or set()
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.promoted: list[str] = []

    async def execute(
        self, query: Any, params: dict[str, Any] | None = None
    ) -> FakeResult:
        sql = str(query)
        self.calls.append((sql, dict(params or {})))
        if "FROM user_entities" in sql and "GROUP BY user_id" in sql:
            return FakeResult(
                [FakeRow(user_id=self.owner_user_id)]
                if self.owner_user_id
                else []
            )
        if "FROM social_events" in sql and "NEW_SUBJECT" in sql:
            return FakeResult(self.candidates)
        if "INSERT INTO user_entities" in sql:
            name = (params or {}).get("name", "")
            if name in self.already_in:
                return FakeResult([])
            self.promoted.append(name)
            return FakeResult([FakeRow(id=uuid4())])
        return FakeResult([])

    async def commit(self) -> None:
        return None


def _install_db_module_path(
    monkeypatch: pytest.MonkeyPatch,
    session: _PromoteSession,
) -> None:
    @asynccontextmanager
    async def fake_get_db():
        yield session

    import backend.database as db_mod

    monkeypatch.setattr(db_mod, "get_db", fake_get_db)


@pytest.mark.unit
def test_auto_promote_skips_when_no_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sess = _PromoteSession(owner_user_id=None, candidates=[])
    _install_db_module_path(monkeypatch, sess)
    import asyncio
    asyncio.run(_auto_promote_subjects())
    assert sess.promoted == []


@pytest.mark.unit
def test_auto_promote_inserts_qualifying_subjects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cands = [
        FakeRow(
            subject="Telangana", magnitude=33,
            confidence="MED", source_count=4,
        ),
        FakeRow(
            subject="Hyderabad", magnitude=29,
            confidence="MED", source_count=6,
        ),
    ]
    sess = _PromoteSession(
        owner_user_id="11111111-1111-1111-1111-111111111111",
        candidates=cands,
    )
    _install_db_module_path(monkeypatch, sess)
    import asyncio
    asyncio.run(_auto_promote_subjects())
    assert set(sess.promoted) == {"Telangana", "Hyderabad"}


@pytest.mark.unit
def test_auto_promote_skips_already_existing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cands = [
        FakeRow(
            subject="Kaleshwaram", magnitude=12,
            confidence="MED", source_count=3,
        ),
        FakeRow(
            subject="Bengaluru", magnitude=13,
            confidence="MED", source_count=6,
        ),
    ]
    sess = _PromoteSession(
        owner_user_id="11111111-1111-1111-1111-111111111111",
        candidates=cands,
        already_in={"Bengaluru"},
    )
    _install_db_module_path(monkeypatch, sess)
    import asyncio
    asyncio.run(_auto_promote_subjects())
    assert sess.promoted == ["Kaleshwaram"]


@pytest.mark.unit
def test_auto_promote_threshold_is_in_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The min_occ + min_src thresholds must be passed as params."""
    sess = _PromoteSession(
        owner_user_id="11111111-1111-1111-1111-111111111111",
        candidates=[],
    )
    _install_db_module_path(monkeypatch, sess)
    import asyncio
    asyncio.run(_auto_promote_subjects())
    candidate_call = next(
        (c for c in sess.calls if "NEW_SUBJECT" in c[0]), None
    )
    assert candidate_call is not None
    params = candidate_call[1]
    assert params.get("min_occ") == 8  # _PROMOTE_MIN_OCC
    assert params.get("min_src") == 3  # _PROMOTE_MIN_SOURCES


# ── Broadened baselines (entity + geo + topic seeds) ─────────────────────


class _BaselineSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def execute(
        self, query: Any, params: dict[str, Any] | None = None
    ) -> FakeResult:
        self.calls.append((str(query), dict(params or {})))
        return FakeResult([])

    async def commit(self) -> None:
        return None


@pytest.mark.unit
def test_recompute_baselines_runs_three_phases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wipe + entity-baseline insert + seed-baseline insert."""
    sess = _BaselineSession()
    _install_db_module_path(monkeypatch, sess)
    import asyncio
    asyncio.run(_recompute_baselines())

    sql_blob = " ".join(c[0] for c in sess.calls)
    # Phase 1: wipe
    assert "DELETE FROM social_entity_baselines" in sql_blob
    # Phase 2: entity-driven baseline
    assert "UNNEST(matched_entities)" in sql_blob
    # Phase 3: geo + topic seed baseline (CROSS JOIN over UNION'd seeds)
    assert "social_geo_seeds" in sql_blob
    assert "social_topic_seeds" in sql_blob
    assert "CROSS JOIN seeds" in sql_blob


@pytest.mark.unit
def test_seeds_returns_geo_and_topic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    geo = [
        FakeRow(id=1, term="Hyderabad", kind="city", weight=15),
        FakeRow(id=2, term="Telangana", kind="state", weight=15),
    ]
    topic = [
        FakeRow(id=1, term="protest", weight=15, note="civil unrest"),
        FakeRow(id=2, term="encounter", weight=15, note="security"),
    ]
    install_fake_db(monkeypatch, FakeSession(responses=[geo, topic]))
    body = TestClient(make_app()).get("/api/signals/seeds").json()
    assert {s["term"] for s in body["geo"]} == {"Hyderabad", "Telangana"}
    assert {s["term"] for s in body["topic"]} == {"protest", "encounter"}
