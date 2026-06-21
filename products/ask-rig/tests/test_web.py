"""Unit tests for Set 3 web layer: fuse, SSRF guard, search parsing (no network)."""
from __future__ import annotations

import app.web.extract as extract_mod
from app.schemas import RetrievedDoc
from app.schemas_account import WebResult
from app.web.extract import is_safe_url
from app.web.fuse import fuse_web_corpus, web_to_doc
from app.web.search import _parse


def _doc(doc_id):
    return RetrievedDoc(
        id=doc_id, title="t", snippet="s", url=None, published_at=None,
        source_id="src", language="en", score=1.0, vec_rank=None, lex_rank=None,
    )


# ---- fuse ----
def test_web_to_doc_provenance():
    d = web_to_doc(WebResult(title="T", url="http://x", snippet="snip", engine="g"), 0)
    assert d.id == "web:0" and d.source_id == "web" and d.url == "http://x"


def test_fuse_interleaves_corpus_and_web():
    corpus = [_doc("c1"), _doc("c2")]
    web = [WebResult(title="W1", url="http://w1"), WebResult(title="W2", url="http://w2")]
    fused = fuse_web_corpus(corpus, web)
    ids = [d.id for d in fused]
    assert set(ids) == {"c1", "c2", "web:0", "web:1"}
    # rank-1 of each list (c1, web:0) outrank rank-2 (c2, web:1) under RRF
    assert ids.index("c1") < ids.index("c2")
    assert ids.index("web:0") < ids.index("web:1")


def test_fuse_empty_web_returns_corpus_only():
    corpus = [_doc("c1")]
    fused = fuse_web_corpus(corpus, [])
    assert [d.id for d in fused] == ["c1"]


# ---- SSRF guard ----
def test_ssrf_blocks_non_http_scheme():
    assert is_safe_url("ftp://example.com/x") is False
    assert is_safe_url("file:///etc/passwd") is False


def test_ssrf_blocks_private_and_loopback(monkeypatch):
    def fake_getaddrinfo(host, *a, **k):
        mapping = {"internal": "10.0.0.5", "lh": "127.0.0.1", "lan": "192.168.1.1"}
        return [(2, 1, 6, "", (mapping[host], 0))]

    monkeypatch.setattr(extract_mod.socket, "getaddrinfo", fake_getaddrinfo)
    assert is_safe_url("http://internal/") is False
    assert is_safe_url("http://lh/") is False
    assert is_safe_url("http://lan/") is False


def test_ssrf_allows_public(monkeypatch):
    monkeypatch.setattr(
        extract_mod.socket, "getaddrinfo",
        lambda host, *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )
    assert is_safe_url("https://example.com/article") is True


# ---- search parsing ----
def test_search_parse_skips_urlless_and_caps():
    raw = [
        {"title": "A", "url": "http://a", "content": "ca", "engine": "g"},
        {"title": "B", "url": "", "content": "cb"},  # dropped (no url)
        {"title": "C", "url": "http://c"},
    ]
    out = _parse(raw, k=10)
    assert [r.url for r in out] == ["http://a", "http://c"]
    assert out[0].engine == "g"


def test_search_parse_respects_k():
    raw = [{"title": str(i), "url": f"http://{i}"} for i in range(10)]
    assert len(_parse(raw, k=3)) == 3
