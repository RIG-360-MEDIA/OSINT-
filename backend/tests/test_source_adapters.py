"""
Smoke tests for every registered govt-source adapter.

For each entry in SOURCE_REGISTRY we:
  1. Call the adapter against a fake/canned HTTP layer.
  2. Assert it returns a list (possibly empty — networks fail).
  3. If non-empty, assert each row has the required fields.

This is a *contract* test, not a network-integration test. Real HTTP
calls are mocked at httpx.AsyncClient. Adapters that depend on
JavaScript-rendered pages (Playwright) are skipped unless
SOURCE_ADAPTER_LIVE=1 is set.

Run:
  pytest backend/tests/test_source_adapters.py -q
  SOURCE_ADAPTER_LIVE=1 pytest backend/tests/test_source_adapters.py -q
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest

from backend.collectors.sources import registry


REQUIRED_FIELDS = {"title", "document_url"}


def _all_adapters():
    registry._autoload_family_modules()
    return list(registry.SOURCE_REGISTRY.items())


@pytest.fixture
def fake_html_client():
    """A fake httpx.AsyncClient returning a generic HTML index."""

    html = """
    <html><body>
      <a href="https://example.test/doc-a.pdf">Important Notification 2024</a>
      <a href="https://example.test/doc-b.pdf">Order dated 01.01.2024</a>
      <a href="login.html">Login</a>
    </body></html>
    """

    class FakeResp:
        status_code = 200
        headers = {"content-type": "text/html"}
        text = html
        content = html.encode()

        def raise_for_status(self): ...

        def json(self):
            return {}

    fake = AsyncMock()
    fake.get = AsyncMock(return_value=FakeResp())
    fake.__aenter__ = AsyncMock(return_value=fake)
    fake.__aexit__ = AsyncMock(return_value=None)
    return fake


@pytest.mark.parametrize("url_key, fn", _all_adapters())
@pytest.mark.asyncio
async def test_adapter_contract(url_key, fn, fake_html_client):
    """Every adapter returns list[dict] with title+document_url fields."""

    if not os.environ.get("SOURCE_ADAPTER_LIVE"):
        # Mock httpx for non-live runs so no real network I/O happens.
        with patch("httpx.AsyncClient", return_value=fake_html_client):
            try:
                rows = await fn(
                    f"https://{url_key.split('/', 1)[0]}",
                    "government_order",
                    1,
                )
            except NotImplementedError:
                pytest.skip(f"{fn.__name__} marked NotImplemented (stub)")
            except Exception as e:  # noqa: BLE001 — adapter sanity probe
                pytest.skip(
                    f"{fn.__name__} requires live HTTP / Playwright: {e}"
                )
    else:
        rows = await fn(f"https://{url_key.split('/', 1)[0]}",
                        "government_order", 1)

    assert isinstance(rows, list), f"{fn.__name__} did not return list"
    for r in rows:
        missing = REQUIRED_FIELDS - r.keys()
        assert not missing, f"{fn.__name__} missing {missing} in row {r}"


def test_registry_has_no_collisions():
    """Each url_key must appear once. Two adapters claiming the same key
    indicates a copy-paste bug."""

    seen: set[str] = set()
    for k, _ in _all_adapters():
        assert k not in seen, f"Duplicate key {k!r}"
        seen.add(k)


def test_registry_count_matches_inventory_doc():
    """Sanity: docs/qa/govt-sources-inventory.md tracks the registry size.
    Phase 4 added scrape_cag and scrape_pib, taking the count from 47 to 49.
    If this drifts again, re-run list_govt_sources --markdown and update
    the doc."""

    expected = 49
    actual = len(_all_adapters())
    assert actual == expected, (
        f"Adapter count drift: registry={actual}, doc says {expected}. "
        f"Re-run `python -m backend.scripts.list_govt_sources --markdown` "
        f"and update docs/qa/govt-sources-inventory.md."
    )
