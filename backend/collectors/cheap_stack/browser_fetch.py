"""Browser-impersonating HTTP fetch (curl_cffi).

The core of the "cheap stack": replicates Chrome's TLS/JA3 + HTTP/2 fingerprint
so requests that plain `requests`/`urllib` get blocked for (Cloudflare, bot walls)
pass through at the network layer — with NO proxy.

Does NOT solve JavaScript challenges ("checking your browser"); for those, a
stealth browser must mint a `cf_clearance` cookie which can then be passed here
via `cookies=`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

try:
    from curl_cffi import requests as cffi_requests
except ImportError as exc:  # fail fast, clear message
    raise ImportError(
        "curl_cffi is required for the cheap stack: pip install curl_cffi"
    ) from exc

# Rotate across a few recent real browser signatures. curl_cffi ships these
# impersonation targets; keep to ones broadly supported by 0.13.x.
_IMPERSONATE_TARGETS = ("chrome", "chrome124", "safari17_0", "edge101")

DEFAULT_TIMEOUT = 20


@dataclass(frozen=True)
class FetchResult:
    """Immutable result of a fetch attempt."""

    ok: bool
    status: int
    url: str
    text: str
    error: Optional[str] = None

    @property
    def json(self) -> Any:
        import json as _json

        return _json.loads(self.text)


def fetch(
    url: str,
    *,
    impersonate: str = "chrome",
    timeout: int = DEFAULT_TIMEOUT,
    headers: Optional[dict] = None,
    cookies: Optional[dict] = None,
    params: Optional[dict] = None,
    proxies: Optional[dict] = None,
) -> FetchResult:
    """Fetch a URL impersonating a real browser.

    `proxies` routes egress (e.g. {"https": "http://user:pass@host:port"}) — used
    to send blocked platforms (Instagram) through a residential exit when the host
    is on a datacenter IP. None = direct.

    Returns a FetchResult (never raises for HTTP errors — inspect .ok/.status).
    Only raises for programmer errors (bad args).
    """
    if not url or not url.startswith(("http://", "https://")):
        raise ValueError(f"invalid url: {url!r}")

    try:
        resp = cffi_requests.get(
            url,
            impersonate=impersonate,
            timeout=timeout,
            headers=headers,
            cookies=cookies,
            params=params,
            proxies=proxies,
        )
    except Exception as exc:  # network/TLS/timeout — report, don't crash caller
        return FetchResult(
            ok=False, status=0, url=url, text="", error=f"{type(exc).__name__}: {exc}"
        )

    return FetchResult(
        ok=resp.status_code < 400,
        status=resp.status_code,
        url=url,
        text=resp.text,
    )


def fetch_with_fallback(url: str, **kwargs) -> FetchResult:
    """Try each impersonation target until one returns a non-blocked response.

    Some anti-bot systems key on specific fingerprints; rotating helps.
    """
    last: Optional[FetchResult] = None
    for target in _IMPERSONATE_TARGETS:
        result = fetch(url, impersonate=target, **kwargs)
        if result.ok:
            return result
        last = result
    return last or FetchResult(ok=False, status=0, url=url, text="", error="all targets failed")
