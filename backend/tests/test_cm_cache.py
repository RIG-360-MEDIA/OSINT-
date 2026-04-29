"""Unit tests for backend.nlp.cm.cache TTL behaviour."""
from __future__ import annotations

import os
import time

import pytest

from backend.nlp.cm import cache


def setup_function(_) -> None:
    cache.invalidate()


def test_put_then_get_returns_value() -> None:
    cache.put("pulse", ("u1", "TG", "24h"), {"score": 0.5})
    assert cache.get("pulse", ("u1", "TG", "24h")) == {"score": 0.5}


def test_get_returns_none_for_unknown_key() -> None:
    assert cache.get("pulse", ("u1", "TG", "24h")) is None


def test_invalidate_section_only_drops_section_keys() -> None:
    cache.put("pulse", ("u1",), 1)
    cache.put("issues", ("u1",), 2)
    dropped = cache.invalidate("pulse")
    assert dropped == 1
    assert cache.get("pulse", ("u1",)) is None
    assert cache.get("issues", ("u1",)) == 2


def test_env_overrides_ttl_and_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CM_TTL_PULSE_S", "1")
    cache.put("pulse", ("u2",), {"x": 1})
    assert cache.get("pulse", ("u2",)) == {"x": 1}
    time.sleep(1.1)
    assert cache.get("pulse", ("u2",)) is None


def test_stats_buckets_by_section() -> None:
    cache.put("pulse", ("u1",), 1)
    cache.put("pulse", ("u2",), 2)
    cache.put("issues", ("u1",), 3)
    s = cache.stats()
    assert s.get("pulse") == 2
    assert s.get("issues") == 1
