"""Collector framework — swap-able methods + normalized output + egress routing.

Each platform Collector holds an ORDERED list of Methods (primary first). When a
method breaks (Instagram rotates doc_ids, a 3rd-party API dies), you add/reorder
methods without touching the pipeline. Every method returns the same normalized
`ProfileResult`, so downstream code is platform-agnostic.

Egress: pass a residential proxy for platforms that 403 datacenter IPs. The
collector is IP-aware by construction — same code runs direct on a residential
box or via relay on Hetzner.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class Egress:
    """How to route outbound requests. Immutable."""

    proxies: Optional[dict] = None          # {"https": "http://user:pass@host:port"}
    label: str = "direct"

    @property
    def is_direct(self) -> bool:
        return not self.proxies


@dataclass(frozen=True)
class ProfileResult:
    """Normalized profile across all platforms. Immutable."""

    platform: str
    handle: str
    ok: bool
    method: str
    display_name: Optional[str] = None
    followers: Optional[int] = None
    following: Optional[int] = None
    posts_count: Optional[int] = None
    bio: Optional[str] = None
    verified: Optional[bool] = None
    external_url: Optional[str] = None
    error: Optional[str] = None
    extra: dict = field(default_factory=dict)


@runtime_checkable
class Method(Protocol):
    """A single collection strategy for a platform."""

    name: str

    def fetch_profile(self, handle: str, egress: Egress) -> Optional[ProfileResult]:
        ...


class Collector:
    """Runs ordered methods until one succeeds. Platform-agnostic to callers."""

    platform: str = "base"

    def __init__(self, methods: list[Method]):
        if not methods:
            raise ValueError("Collector needs at least one method")
        self._methods = list(methods)

    @property
    def method_names(self) -> list[str]:
        return [m.name for m in self._methods]

    def profile(self, handle: str, egress: Optional[Egress] = None) -> ProfileResult:
        """Try each method in order; return the first OK result.

        If all fail, return a failed ProfileResult carrying the last error so the
        caller always gets a normalized object (never None, never a raw exception).
        """
        if not handle:
            raise ValueError("handle required")
        egress = egress or Egress()

        last_error = "no method produced a result"
        for method in self._methods:
            try:
                result = method.fetch_profile(handle, egress)
            except Exception as exc:  # a broken method must not kill the chain
                last_error = f"{method.name}: {type(exc).__name__}: {exc}"
                continue
            if result and result.ok:
                return result
            if result and result.error:
                last_error = f"{method.name}: {result.error}"

        return ProfileResult(
            platform=self.platform, handle=handle, ok=False,
            method="none", error=last_error,
        )
