"""
Golden tests for backend.nlp.govt_intel.

- Unit tests for compute_intrinsic_importance (pure function, deterministic).
- Schema validation tests for GovtDocIntel (lenient date / list coercion).
- Integration tests that call extract_intel() against real govt-doc samples
  pulled from the local DB; these auto-skip if the DB or Groq is unreachable.

Run:
    docker exec rig-backend pytest backend/tests/test_govt_intel.py -v
"""
from __future__ import annotations

import asyncio
import os
from typing import get_args

import pytest

from backend.nlp.govt_intel import compute_intrinsic_importance, extract_intel
from backend.nlp.govt_intel_schema import (
    ActionPosture,
    DocumentNature,
    EnforcementStrength,
    GovtDocIntel,
)

_DOC_NATURES = set(get_args(DocumentNature))
_ACTION_POSTURES = set(get_args(ActionPosture))
_ENFORCEMENT = set(get_args(EnforcementStrength))


# ── Unit tests: compute_intrinsic_importance ───────────────────────────────────

@pytest.mark.unit
def test_intrinsic_importance_max_order_binding_precedent():
    """ORDER (1.00) + BINDING (+0.05) + precedent (+0.05) clips at 1.0."""
    intel = GovtDocIntel(
        what_it_does="x",
        document_nature="ORDER",
        enforcement_strength="BINDING",
        precedent_setting=True,
    )
    score = compute_intrinsic_importance(intel)
    assert score == pytest.approx(1.0, abs=0.01)


@pytest.mark.unit
def test_intrinsic_importance_min_other_routine():
    """OTHER (0.20) - ROUTINE_ADMIN (-0.15) ~ 0.05."""
    intel = GovtDocIntel(
        what_it_does="x",
        document_nature="OTHER",
        action_posture="ROUTINE_ADMIN",
    )
    score = compute_intrinsic_importance(intel)
    assert score == pytest.approx(0.05, abs=0.01)


@pytest.mark.unit
def test_intrinsic_importance_bounded_0_to_1():
    """No combination of inputs may push the score outside [0,1]."""
    intel = GovtDocIntel(
        what_it_does="x",
        document_nature="ORDER",
        enforcement_strength="BINDING",
        precedent_setting=True,
        financial_magnitude_inr=10_000_000_000_000,  # absurd ₹10 lakh crore
        geography_affected=["India"],
    )
    score = compute_intrinsic_importance(intel)
    assert 0.0 <= score <= 1.0


@pytest.mark.unit
def test_intrinsic_importance_money_bump_is_log_scaled():
    """Larger money -> larger bump, but log-scaled (not linear)."""
    base = GovtDocIntel(what_it_does="x", document_nature="NOTIFICATION")
    one_cr = GovtDocIntel(
        what_it_does="x", document_nature="NOTIFICATION",
        financial_magnitude_inr=10_000_000,
    )
    hundred_cr = GovtDocIntel(
        what_it_does="x", document_nature="NOTIFICATION",
        financial_magnitude_inr=1_000_000_000,
    )
    s_base = compute_intrinsic_importance(base)
    s_1cr = compute_intrinsic_importance(one_cr)
    s_100cr = compute_intrinsic_importance(hundred_cr)
    assert s_base < s_1cr < s_100cr


# ── Schema tests: GovtDocIntel coercion ────────────────────────────────────────

@pytest.mark.unit
def test_schema_lenient_date_parsing():
    """Empty strings, 'null', and bad dates coerce to None instead of raising."""
    intel = GovtDocIntel(
        what_it_does="test",
        effective_date="",
        deadline_dates=["2025-12-31", "", "not-a-date", None, "2026-01-15"],
    )
    assert intel.effective_date is None
    assert len(intel.deadline_dates) == 2


@pytest.mark.unit
def test_schema_invalid_enum_falls_back_to_other():
    """Unknown nature/posture coerces to OTHER rather than raising."""
    intel = GovtDocIntel(
        what_it_does="test",
        document_nature="MYSTERY_DOC_TYPE",
        action_posture="WHATEVER",
        enforcement_strength="MAYBE",
    )
    assert intel.document_nature == "OTHER"
    assert intel.action_posture == "OTHER"
    assert intel.enforcement_strength is None


@pytest.mark.unit
def test_schema_money_coercion():
    """String numerics coerce; junk yields None."""
    assert GovtDocIntel(
        what_it_does="x", financial_magnitude_inr="8470000000",
    ).financial_magnitude_inr == 8470000000
    assert GovtDocIntel(
        what_it_does="x", financial_magnitude_inr="not a number",
    ).financial_magnitude_inr is None
    assert GovtDocIntel(
        what_it_does="x", financial_magnitude_inr=-5,
    ).financial_magnitude_inr is None


# ── Integration tests against real DB samples ──────────────────────────────────

def _maybe_load_db_samples() -> list[tuple[str, str]]:
    """Pull up to 3 longest govt-doc samples from the live DB.

    Returns [] if anything goes wrong (no DB, no env, no docs) so the
    integration tests cleanly skip rather than crash CI.
    """
    try:
        from sqlalchemy import text  # noqa: WPS433
        from backend.database import get_db  # noqa: WPS433
    except Exception:
        return []

    async def _fetch():
        try:
            async with get_db() as db:
                rows = (await db.execute(text(
                    "SELECT title, "
                    "COALESCE(full_text_translated, full_text) AS body "
                    "FROM govt_documents "
                    "WHERE COALESCE(full_text_translated, full_text) IS NOT NULL "
                    "  AND length(COALESCE(full_text_translated, full_text)) > 1000 "
                    "ORDER BY length(full_text) DESC NULLS LAST "
                    "LIMIT 3"
                ))).fetchall()
                return [(r.title or "Untitled", r.body) for r in rows]
        except Exception:
            return []

    try:
        return asyncio.run(_fetch())
    except Exception:
        return []


_SAMPLES = _maybe_load_db_samples() if os.getenv("RUN_LIVE_GROQ_TESTS") else []


@pytest.mark.integration
@pytest.mark.skipif(
    not _SAMPLES,
    reason="Set RUN_LIVE_GROQ_TESTS=1 and ensure DB is reachable to run live extraction tests.",
)
@pytest.mark.parametrize("idx", range(len(_SAMPLES) or 1))
def test_extract_intel_live_sample(idx: int):
    """Live Groq call against a real govt-doc sample."""
    title, body = _SAMPLES[idx]
    intel = asyncio.run(extract_intel(body, title))

    # Hard guarantees from the schema regardless of Groq quality
    assert isinstance(intel, GovtDocIntel)
    assert isinstance(intel.what_it_does, str) and intel.what_it_does.strip()
    assert intel.document_nature in _DOC_NATURES
    assert intel.action_posture in _ACTION_POSTURES
    if intel.enforcement_strength is not None:
        assert intel.enforcement_strength in _ENFORCEMENT

    score = compute_intrinsic_importance(intel)
    assert 0.0 <= score <= 1.0


@pytest.mark.integration
@pytest.mark.skipif(
    not _SAMPLES,
    reason="Set RUN_LIVE_GROQ_TESTS=1 and ensure DB is reachable to run live extraction tests.",
)
def test_extract_intel_at_least_one_sample_has_money():
    """Across the sampled docs, at least one should mention a rupee figure
    that Groq can convert. If none do, this test xfails rather than failing
    — it's a smoke test of extraction quality, not a hard contract."""
    populated = 0
    for title, body in _SAMPLES:
        intel = asyncio.run(extract_intel(body, title))
        if intel.financial_magnitude_inr is not None:
            populated += 1
    if populated == 0:
        pytest.xfail("No sample produced a financial_magnitude_inr value.")
    assert populated >= 1


# ── Fallback path test (no live Groq required) ─────────────────────────────────

@pytest.mark.unit
def test_extract_intel_returns_default_on_groq_failure(monkeypatch):
    """When extract_json raises, extract_intel falls back to a minimal
    GovtDocIntel(what_it_does=title) instead of propagating the error."""
    from backend.nlp import govt_intel as mod
    from backend.nlp.groq_client import GroqQuotaExhausted

    async def _fail(*_args, **_kwargs):
        raise GroqQuotaExhausted("test")

    monkeypatch.setattr(mod, "extract_json", _fail)

    intel = asyncio.run(extract_intel("body text", "My Test Title"))
    assert isinstance(intel, GovtDocIntel)
    assert intel.what_it_does == "My Test Title"
    assert intel.document_nature == "OTHER"
    assert intel.action_posture == "OTHER"
    score = compute_intrinsic_importance(intel)
    assert 0.0 <= score <= 1.0
