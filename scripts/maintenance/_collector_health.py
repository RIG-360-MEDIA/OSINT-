"""Probe the cookie-dependent cheap_stack keyword collectors so an expired session
NEVER fails silently.

Runs INSIDE rig-backend (has the collectors + the session cookies). Prints one line per
platform and exits 2 if any cookie platform is unhealthy — the watchdog turns that into an
ALERT telling you which cookie to refresh. A tiny probe (limit=2) that also keeps the
sessions warm.

    docker exec -w /app rig-backend python scripts/maintenance/_collector_health.py
"""
from __future__ import annotations

import asyncio
import sys

from backend.collectors.cheap_stack.keyword_search import REGISTRY

# The platforms whose keyword search depends on a session cookie that can expire.
COOKIE_PLATFORMS = ("reddit", "twitter", "instagram")
PROBE_KW = "india"   # trivial, always-matching keyword


async def _probe(platform: str) -> tuple[str, bool, str]:
    fn = REGISTRY.get(platform)
    if fn is None:
        return platform, False, "not in REGISTRY"
    try:
        r = await fn(PROBE_KW, limit=2)
    except Exception as exc:                       # any failure = report, never crash
        return platform, False, f"{type(exc).__name__}: {exc}"[:120]
    ok = bool(getattr(r, "ok", False))
    detail = getattr(r, "error", None) or f"count={getattr(r, 'count', 0)}"
    return platform, ok, detail


async def main() -> None:
    results = await asyncio.gather(*(_probe(p) for p in COOKIE_PLATFORMS))
    bad = []
    for platform, ok, detail in results:
        print(f"{platform} ok={ok} {detail}")
        if not ok:
            bad.append(f"{platform} ({detail})")
    if bad:
        print("FAIL " + " | ".join(bad))
        sys.exit(2)
    print("OK")


if __name__ == "__main__":
    asyncio.run(main())
