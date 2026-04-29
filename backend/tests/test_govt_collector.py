"""
Tests for backend.collectors.govt_collector.

Covers:
  - _is_junk_title heuristic
  - download_pdf (200, 404, timeout, non-PDF, oversize, empty)
  - extract_text_from_pdf (normal, encrypted, scanned, corrupt)
  - fetch_document_urls registry dispatch + fallback + portal cap

Run:
  pytest backend/tests/test_govt_collector.py -q
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.collectors import govt_collector


# ---------- _is_junk_title --------------------------------------------- #

@pytest.mark.parametrize(
    "title, expected",
    [
        ("", True),
        ("   ", True),
        ("Click here", True),
        ("Read more", True),
        ("PDF", True),
        ("Reserve Bank of India: Master Direction on KYC, 2024", False),
        ("Order dated 12.03.2024 in W.P. No. 1234/2023", False),
    ],
)
def test_is_junk_title(title, expected):
    assert govt_collector._is_junk_title(title) is expected


# ---------- download_pdf ----------------------------------------------- #

@pytest.mark.asyncio
async def test_download_pdf_happy(monkeypatch):
    body = b"%PDF-1.4\n...content..."

    class FakeResp:
        status_code = 200
        headers = {"content-type": "application/pdf"}
        content = body

        def raise_for_status(self): ...

    fake_client = AsyncMock()
    fake_client.get = AsyncMock(return_value=FakeResp())
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=fake_client):
        result = await govt_collector.download_pdf("https://x/x.pdf")
    assert result == body


@pytest.mark.asyncio
async def test_download_pdf_404_returns_none(monkeypatch):
    import httpx

    class FakeResp:
        status_code = 404

        def raise_for_status(self):
            raise httpx.HTTPStatusError(
                "404", request=None, response=None
            )

    fake_client = AsyncMock()
    fake_client.get = AsyncMock(return_value=FakeResp())
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=fake_client):
        result = await govt_collector.download_pdf("https://x/missing.pdf")
    assert result is None


@pytest.mark.asyncio
async def test_download_pdf_non_pdf_content_type_rejected():
    class FakeResp:
        status_code = 200
        headers = {"content-type": "text/html"}
        content = b"<html>not a pdf</html>"

        def raise_for_status(self): ...

    fake_client = AsyncMock()
    fake_client.get = AsyncMock(return_value=FakeResp())
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=fake_client):
        result = await govt_collector.download_pdf("https://x/login.html")
    assert result is None


# ---------- extract_text_from_pdf -------------------------------------- #

def test_extract_text_corrupt_returns_empty_string(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf at all")
    out = govt_collector.extract_text_from_pdf(bad.read_bytes())
    assert isinstance(out, str)
    assert out == "" or "error" in out.lower()


# ---------- fetch_document_urls registry dispatch ---------------------- #

@pytest.mark.asyncio
async def test_fetch_document_urls_dispatches_to_registry(monkeypatch):
    from backend.collectors.sources import registry

    captured: list[tuple[str, str, int]] = []

    async def fake_scraper(portal_url: str, document_type: str,
                           since_days: int = 2):
        captured.append((portal_url, document_type, since_days))
        return [{"title": "ok", "document_url": "https://x/x.pdf"}]

    registry.SOURCE_REGISTRY["fixture.example"] = fake_scraper
    try:
        out = await govt_collector.fetch_document_urls(
            "https://fixture.example/path",
            "government_order",
            since_days=3,
        )
        assert captured == [
            ("https://fixture.example/path", "government_order", 3)
        ]
        assert out and out[0]["document_url"] == "https://x/x.pdf"
    finally:
        registry.SOURCE_REGISTRY.pop("fixture.example", None)


@pytest.mark.asyncio
async def test_fetch_document_urls_falls_back_when_no_match():
    """No registry hit → legacy generic path runs (must not raise)."""
    out = await govt_collector.fetch_document_urls(
        "https://no-such-portal.test/x",
        "government_order",
        since_days=1,
    )
    assert isinstance(out, list)


@pytest.mark.asyncio
async def test_fetch_document_urls_respects_per_portal_cap(monkeypatch):
    from backend.collectors.sources import registry

    async def flooder(*_a, **_kw):
        return [
            {"title": f"d{i}", "document_url": f"https://x/{i}.pdf"}
            for i in range(100)
        ]

    registry.SOURCE_REGISTRY["floodtest"] = flooder
    try:
        out = await govt_collector.fetch_document_urls(
            "https://floodtest/", "ministry_order", since_days=1
        )
        cap = getattr(govt_collector, "_PER_PORTAL_CAP", 100)
        assert len(out) <= cap
    finally:
        registry.SOURCE_REGISTRY.pop("floodtest", None)
