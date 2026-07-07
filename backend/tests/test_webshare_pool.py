"""Unit tests for the Webshare account-pool parser (transcript rotation).

Pure parsing, no network. Validates that pooled + legacy creds combine,
malformed entries are skipped, and duplicates collapse — so a live PASS on the
rotation is trustworthy.

    pytest backend/tests/test_webshare_pool.py -v
"""
from __future__ import annotations

import pytest

from backend.collectors.youtube_v2.transcript import _webshare_accounts


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for k in ("WEBSHARE_ACCOUNTS", "WEBSHARE_USER", "WEBSHARE_PASS"):
        monkeypatch.delenv(k, raising=False)


def test_parses_pool(monkeypatch):
    monkeypatch.setenv("WEBSHARE_ACCOUNTS", "u1:p1,u2:p2,u3:p3")
    assert _webshare_accounts() == [("u1", "p1"), ("u2", "p2"), ("u3", "p3")]


def test_legacy_single_still_honored(monkeypatch):
    monkeypatch.setenv("WEBSHARE_USER", "solo")
    monkeypatch.setenv("WEBSHARE_PASS", "secret")
    assert _webshare_accounts() == [("solo", "secret")]


def test_pool_plus_legacy_combined(monkeypatch):
    monkeypatch.setenv("WEBSHARE_ACCOUNTS", "u1:p1,u2:p2")
    monkeypatch.setenv("WEBSHARE_USER", "legacy")
    monkeypatch.setenv("WEBSHARE_PASS", "lp")
    assert _webshare_accounts() == [("u1", "p1"), ("u2", "p2"), ("legacy", "lp")]


def test_malformed_entries_skipped(monkeypatch):
    # missing colon, empty user, empty pass, stray whitespace
    monkeypatch.setenv("WEBSHARE_ACCOUNTS", "nocolon, :nopass, nouser:, u1 : p1 ,,")
    assert _webshare_accounts() == [("u1", "p1")]


def test_duplicates_collapse(monkeypatch):
    monkeypatch.setenv("WEBSHARE_ACCOUNTS", "u1:p1,u1:p1,u2:p2")
    monkeypatch.setenv("WEBSHARE_USER", "u2")
    monkeypatch.setenv("WEBSHARE_PASS", "p2")
    assert _webshare_accounts() == [("u1", "p1"), ("u2", "p2")]


def test_empty_env_gives_empty_pool():
    assert _webshare_accounts() == []
