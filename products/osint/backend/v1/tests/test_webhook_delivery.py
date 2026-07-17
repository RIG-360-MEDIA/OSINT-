"""No-DB / no-network coverage for webhook_delivery.py."""
from __future__ import annotations

import asyncio
import datetime

from _fakes import _DBCtx, FakeSession  # noqa: E402

from v1 import webhook_delivery as wd  # noqa: E402


def _dt():
    return datetime.datetime(2026, 6, 30, 12, 0, tzinfo=datetime.timezone.utc)


# ── _ssrf_ok / _sign ────────────────────────────────────────────────────────

def test_ssrf_ok_rejects_non_https_and_bad_host(monkeypatch):
    assert wd._ssrf_ok("http://example.com") is False
    assert wd._ssrf_ok("not a url") is False
    assert wd._ssrf_ok("https://") is False


def test_ssrf_ok_public_ip(monkeypatch):
    monkeypatch.setattr(wd.socket, "getaddrinfo",
                        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    assert wd._ssrf_ok("https://example.com") is True


def test_ssrf_ok_private_ip_blocked(monkeypatch):
    monkeypatch.setattr(wd.socket, "getaddrinfo",
                        lambda *a, **k: [(2, 1, 6, "", ("10.0.0.1", 443))])
    assert wd._ssrf_ok("https://internal.example") is False


def test_sign_is_hmac():
    sig = wd._sign("secret", b"body")
    assert sig.startswith("sha256=") and len(sig) == len("sha256=") + 64


# ── run_once: delivery paths ────────────────────────────────────────────────

class _Resp:
    def __init__(self, code):
        self.status_code = code


class _FakeClient:
    def __init__(self, code=200, raise_exc=False):
        self._code = code
        self._raise = raise_exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, content=None, timeout=None, headers=None):
        if self._raise:
            raise ConnectionError("boom")
        return _Resp(self._code)


def _hook_row(url="https://ok.example"):
    return {"id": "11111111-1111-1111-1111-111111111111", "url": url,
            "filter": {"topic": "POLITICS", "entity": "22222222-2222-2222-2222-222222222222",
                       "sentiment": "critical"},
            "last_delivered_at": None, "failure_count": 0,
            "all_entities": False, "entity_ids": ["22222222-2222-2222-2222-222222222222"]}


def _item_row():
    return {"id": "33333333-3333-3333-3333-333333333333", "headline": "H",
            "source": "S", "url": "https://a", "topic": "POLITICS",
            "collected_at": _dt(), "published_at": _dt()}


def _patch(monkeypatch, batches, client):
    """get_db yields sessions from ``batches`` in order; hash_secret + httpx stubbed.

    Each batch is the row-list returned by the SINGLE execute in that get_db()
    block, so we seed the session with ``[batch]`` (one execute -> those rows).
    """
    state = {"i": 0}

    def get_db():
        idx = state["i"]
        state["i"] += 1
        seed = batches[idx] if idx < len(batches) else []
        return _DBCtx(FakeSession([seed]))

    monkeypatch.setattr(wd, "get_db", get_db)
    monkeypatch.setattr(wd, "hash_secret", lambda: "server-secret")
    monkeypatch.setattr(wd.socket, "getaddrinfo",
                        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    monkeypatch.setattr(wd.httpx, "AsyncClient", lambda **k: client)


def test_run_once_delivers(monkeypatch):
    # batches: [hooks], [items for _matching_items], [log], [final update]
    _patch(monkeypatch, [[_hook_row()], [_item_row()], [], []], _FakeClient(200))
    delivered = asyncio.run(wd.run_once())
    assert delivered == 1


def test_run_once_failed_post_retries(monkeypatch):
    async def _nosleep(*_a, **_k):
        return None
    monkeypatch.setattr(wd.asyncio, "sleep", _nosleep)
    _patch(monkeypatch, [[_hook_row()], [_item_row()], [], []], _FakeClient(500))
    delivered = asyncio.run(wd.run_once())
    assert delivered == 0  # 5xx -> never marked delivered


def test_run_once_post_raises(monkeypatch):
    async def _nosleep(*_a, **_k):
        return None
    monkeypatch.setattr(wd.asyncio, "sleep", _nosleep)
    _patch(monkeypatch, [[_hook_row()], [_item_row()], [], []],
           _FakeClient(raise_exc=True))
    delivered = asyncio.run(wd.run_once())
    assert delivered == 0


def test_run_once_ssrf_blocked(monkeypatch):
    # host resolves private -> ssrf blocked branch (deactivate + log, continue)
    _patch(monkeypatch, [[_hook_row()], [], []], _FakeClient(200))
    monkeypatch.setattr(wd.socket, "getaddrinfo",
                        lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 443))])
    delivered = asyncio.run(wd.run_once())
    assert delivered == 0


def test_run_once_all_entities(monkeypatch):
    hook = _hook_row()
    hook["all_entities"] = True
    hook["entity_ids"] = None
    hook["filter"] = {}
    _patch(monkeypatch, [[hook], [_item_row()], [], []], _FakeClient(200))
    assert asyncio.run(wd.run_once()) == 1
