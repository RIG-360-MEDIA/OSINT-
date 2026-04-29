"""Import-level smoke test for the CM router.

Ensures that:
  * cm_router and its companion modules import cleanly (no circular imports).
  * All 16 endpoints + Pydantic schemas are wired.
  * The aggregator endpoint exposes every section field.

Live integration tests would require a running Postgres + the cm_* tables;
they are deferred to the CI smoke job.
"""
from __future__ import annotations

import pytest

from backend.routers import cm_queries, cm_router, cm_schemas


def test_router_prefix_and_tag() -> None:
    assert cm_router.cm_router.prefix == "/api/cm"
    assert "cm" in cm_router.cm_router.tags


def test_dashboard_response_has_all_sections() -> None:
    fields = set(cm_schemas.CMDashboardResponse.model_fields.keys())
    expected_sections = {
        "pulse",
        "issues",
        "silence",
        "spokespersons",
        "cabinet_onmessage",
        "dissent",
        "trajectory",
        "heatmap",
        "promises",
        "counter_narratives",
        "risk_window",
        "quotes",
        "voice_share",
        "language_divergence",
        "medium_divergence",
    }
    assert expected_sections.issubset(fields)


def test_endpoint_paths_complete() -> None:
    paths = {route.path for route in cm_router.cm_router.routes}
    expected = {
        "/api/cm/pulse",
        "/api/cm/issues",
        "/api/cm/silence",
        "/api/cm/spokespersons",
        "/api/cm/cabinet-onmessage",
        "/api/cm/dissent",
        "/api/cm/trajectory",
        "/api/cm/heatmap",
        "/api/cm/promises",
        "/api/cm/counter-narratives",
        "/api/cm/risk-window",
        "/api/cm/quotes",
        "/api/cm/voice-share",
        "/api/cm/divergence/language",
        "/api/cm/divergence/medium",
        "/api/cm/dashboard",
    }
    missing = expected - paths
    assert not missing, f"missing endpoints: {missing}"


@pytest.mark.parametrize(
    "fn_name",
    [
        "fetch_pulse",
        "fetch_issues",
        "fetch_silence",
        "fetch_spokespersons",
        "fetch_dissent",
        "fetch_trajectory",
        "fetch_heatmap",
        "fetch_promises",
        "fetch_counter_narratives",
        "fetch_risk_window",
        "fetch_quotes",
        "fetch_voice_share",
        "fetch_language_divergence",
        "fetch_medium_divergence",
    ],
)
def test_query_helpers_exist(fn_name: str) -> None:
    assert callable(getattr(cm_queries, fn_name))
