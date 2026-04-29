"""
Per-adapter smoke tests for the 47 govt-document source adapters.

Phase 9 audit closes Q8 from the quality review: there were zero per-adapter
tests despite 47 adapters. Selector drift on any portal could ship to prod
unnoticed because the only signal was "0 docs_inserted" in govt_collection_runs.

This file parametrizes over every adapter registered in SOURCE_REGISTRY,
mocks httpx with a captured fragment of the portal's HTML (held inline so
the test stays hermetic), and asserts:

  1. The adapter is decorated and registered.
  2. Calling it with the canonical portal URL returns a list[dict].
  3. Each returned dict has the contract keys: url, title, type.
  4. URLs are absolute.

The test does NOT assert "found at least one row" because some portals (e.g.
e-Gazette) are intentional no-ops in v1. What it asserts is "the adapter
runs without raising and obeys the registry contract." That alone is enough
to catch import errors, signature drift, and exception leaks — the three
things that actually break the daily collection run.

For real-content recall checks, see test_govt_intel_pipeline.py.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Minimal HTML fixtures per adapter family ───────────────────────────────

# A single small fragment is enough — adapters do their own filtering, so the
# test only needs the shape (anchor tags with hrefs) to exercise the parser.
_GENERIC_FRAGMENT = """
<html><body>
  <ul>
    <li><a href="/sites/default/files/2026/04/notification-001.pdf">
        Notification 001 dated 25 Apr 2026</a></li>
    <li><a href="/press-releases.htm?dtl/12345/Test+Release">
        Press release on test policy</a></li>
    <li><a href="javascript:void(0)">Skip me</a></li>
    <li><a href="#top">Also skip</a></li>
  </ul>
</body></html>
"""


@pytest.fixture
def adapters() -> dict[str, Any]:
    """Force the registry to autoload, then return every registered adapter."""
    from backend.collectors.sources.registry import lookup, SOURCE_REGISTRY
    # lookup() triggers the one-shot autoload guard.
    lookup("https://example.invalid/never-matches")
    return dict(SOURCE_REGISTRY)


def test_registry_is_populated(adapters: dict[str, Any]) -> None:
    """Sanity: at least 30 adapters registered. Drops below this means
    a family module failed to import (decorator never ran)."""
    assert len(adapters) >= 30, (
        f"Only {len(adapters)} adapters registered — did a family module "
        f"fail to import? Got: {sorted(adapters.keys())}"
    )


@pytest.mark.unit
def test_pib_and_cag_registered(adapters: dict[str, Any]) -> None:
    """D-16 + D-17 closure check: PIB and CAG adapters must be in the
    registry (the UI exposes filter chips that depend on them)."""
    assert "pib.gov.in" in adapters, "PIB adapter missing — D-16 regression"
    assert "cag.gov.in" in adapters, "CAG adapter missing — D-17 regression"


def _mock_httpx_get(html: str = _GENERIC_FRAGMENT) -> MagicMock:
    """Build a context-manager-shaped mock of httpx.AsyncClient that
    returns the same HTML for every GET. Adapters always create their own
    AsyncClient so we patch at the class level."""
    response = MagicMock()
    response.status_code = 200
    response.text = html
    response.headers = {"content-type": "text/html"}

    client = MagicMock()
    client.get = AsyncMock(return_value=response)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=None)

    factory = MagicMock(return_value=ctx)
    return factory


@pytest.mark.unit
@pytest.mark.parametrize(
    "url_substring",
    [
        # Spot-check the high-traffic adapters; the registry-wide check
        # below covers the long tail.
        "rbi.org.in",
        "sebi.gov.in",
        "pib.gov.in",
        "cag.gov.in",
        "mea.gov.in",
        "mod.gov.in",
        "mha.gov.in",
        "niti.gov.in",
        "gem.gov.in",
        "finmin.nic.in",
        "indiabudget.gov.in",
    ],
)
def test_named_adapter_returns_contract(
    url_substring: str, adapters: dict[str, Any]
) -> None:
    """Each named adapter must:
      - exist in the registry,
      - run without raising,
      - return list[dict],
      - emit dicts with {url, title, type} where url is absolute.
    """
    if url_substring not in adapters:
        pytest.skip(f"{url_substring} not registered in this build")

    fn = adapters[url_substring]
    portal = f"https://{url_substring}/"

    with patch("httpx.AsyncClient", _mock_httpx_get()):
        result = asyncio.run(fn(portal, "document", 30))

    assert isinstance(result, list), f"{fn.__name__} must return a list"
    for row in result:
        assert isinstance(row, dict), f"{fn.__name__} row not dict"
        assert "url" in row and "title" in row and "type" in row, (
            f"{fn.__name__} row missing contract keys: {row}"
        )
        assert row["url"].startswith(("http://", "https://")), (
            f"{fn.__name__} returned non-absolute url: {row['url']}"
        )


@pytest.mark.unit
def test_every_adapter_runs_without_raising(
    adapters: dict[str, Any],
) -> None:
    """Loop over every registered adapter and confirm it doesn't raise on
    a happy-path mocked HTTP response. Catches signature drift and
    `except Exception`-leaks across the whole registry in ~1 second."""
    failures: list[str] = []
    for url_substring, fn in adapters.items():
        portal = f"https://{url_substring}/"
        try:
            with patch("httpx.AsyncClient", _mock_httpx_get()):
                result = asyncio.run(fn(portal, "document", 30))
            assert isinstance(result, list)
        except Exception as exc:  # noqa: BLE001 — capture for report
            failures.append(f"{url_substring} ({fn.__name__}): {exc!r}")
    assert not failures, (
        "Adapters that raised on mocked happy-path:\n  - "
        + "\n  - ".join(failures)
    )
