"""Adapter contracts for Dossier sources.

Every adapter exports `async def fetch(ctx: AdapterContext) -> list[Finding]`.
Adapters MUST NOT raise — they wrap their own errors and return [] on failure.
This keeps `asyncio.gather` fan-out resilient: one slow/dead source can never
poison the whole dossier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol


@dataclass(frozen=True)
class AdapterContext:
    target: str
    target_type: str           # name | email | phone | username | domain | image
    purpose_note: str | None = None
    timeout_s: float = 8.0


@dataclass(frozen=True)
class Finding:
    source: str                # "searxng", "wikidata", "xposedornot", ...
    field: str                 # "bio", "breach", "linked_account", ...
    value: Any                 # JSON-serializable
    source_url: str | None = None
    confidence: float = 0.8


class Adapter(Protocol):
    name: str
    supported_types: tuple[str, ...]

    async def fetch(self, ctx: AdapterContext) -> list[Finding]: ...


AdapterFn = Callable[[AdapterContext], Awaitable[list[Finding]]]


@dataclass(frozen=True)
class AdapterSpec:
    name: str
    supported_types: tuple[str, ...]
    fetch: AdapterFn
    sensitive: bool = False    # requires purpose_note before invocation
