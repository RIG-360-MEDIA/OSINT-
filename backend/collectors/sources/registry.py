"""
Source-Adapter registry.

Each Phase 3 family module imports ``register_source`` and decorates one or
more async scraper functions:

    from backend.collectors.sources.registry import register_source

    @register_source("rbi.org.in")
    async def scrape_rbi_circulars(portal_url: str, document_type: str,
                                    since_days: int = 2) -> list[dict]:
        ...

The dict registry maps a URL substring → an async scraper function with the
shared signature ``(portal_url, document_type, since_days) -> list[dict]``.

`backend/collectors/govt_collector.py:fetch_document_urls` consults this
registry first; if no key matches, it falls back to the original
PIB / Telangana / generic scrapers for backwards compatibility.

Auto-import: every family module under ``backend/collectors/sources/*.py``
(except ``__init__`` and ``registry``) is imported on first lookup so its
``@register_source`` decorators take effect.
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


ScraperFn = Callable[[str, str, int], Awaitable[list[dict]]]

SOURCE_REGISTRY: dict[str, ScraperFn] = {}

_AUTOLOADED = False


def register_source(url_substring: str) -> Callable[[ScraperFn], ScraperFn]:
    """Decorator. Maps a URL substring to a scraper function."""

    def _wrap(fn: ScraperFn) -> ScraperFn:
        if url_substring in SOURCE_REGISTRY:
            logger.warning(
                "Source registry collision on %r — %s overriding %s",
                url_substring,
                fn.__name__,
                SOURCE_REGISTRY[url_substring].__name__,
            )
        SOURCE_REGISTRY[url_substring] = fn
        return fn

    return _wrap


def _autoload_family_modules() -> None:
    """Import every backend.collectors.sources.* module so decorators run.

    Idempotent — guarded by module-level _AUTOLOADED flag.
    """
    global _AUTOLOADED
    if _AUTOLOADED:
        return
    _AUTOLOADED = True

    import backend.collectors.sources as pkg

    for mod_info in pkgutil.iter_modules(pkg.__path__):
        if mod_info.name in {"__init__", "registry"}:
            continue
        try:
            importlib.import_module(f"backend.collectors.sources.{mod_info.name}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to autoload source module %s: %s", mod_info.name, exc
            )


def lookup(portal_url: str) -> ScraperFn | None:
    """Find a matching adapter by substring; auto-loads family modules first."""
    _autoload_family_modules()
    for key, fn in SOURCE_REGISTRY.items():
        if key in portal_url:
            return fn
    return None
