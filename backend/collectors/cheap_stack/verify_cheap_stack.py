"""Live verification of the cheap stack. Run directly:

    python -m backend.collectors.cheap_stack.verify_cheap_stack

Hits real endpoints and prints a PASS/FAIL matrix per technique. No secrets,
no proxies — proves the stack collects with zero paid infra.
"""
from __future__ import annotations

import sys

from . import archive, frontends, oembed
from .browser_fetch import fetch


def _line(name: str, ok: bool, detail: str) -> tuple[bool, str]:
    tag = "PASS" if ok else "FAIL"
    return ok, f"[{tag}] {name:<34} {detail}"


def run() -> int:
    # FREE-CORE tier: unblockable, no auth, must always pass.
    core = []

    # 1. curl_cffi TLS impersonation vs a Cloudflare-fronted site
    r = fetch("https://www.cloudflare.com/", timeout=20)
    core.append(_line("curl_cffi TLS impersonation", r.ok,
                      f"status={r.status} err={r.error or '-'}"))

    # 2. YouTube oEmbed (official, no auth)
    yt = oembed.oembed("youtube", "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    core.append(_line("oEmbed YouTube", bool(yt),
                      f"title={ (yt or {}).get('title','-')[:40] }"))

    # 3. Wayback latest snapshot (historical, unblockable)
    snap = archive.wayback_latest("bbc.com")
    core.append(_line("Wayback latest snapshot", bool(snap),
                      f"ts={ (snap or {}).get('timestamp','-') }"))

    # 3b. Wayback capture history
    hist = archive.wayback_history("bbc.com/news", limit=5)
    core.append(_line("Wayback history (CDX)", len(hist) > 0,
                      f"captures={len(hist)}"))

    # 3c. Common Crawl latest index id
    cc_index = archive.commoncrawl_latest_index()
    core.append(_line("Common Crawl index discovery", bool(cc_index),
                      f"index={cc_index or '-'}"))

    # HARD-PLATFORM tier: known to need last-mile (self-host / stealth / proxy).
    # Informational only — these confirm WHERE the free stack ends.
    hard = []

    tk = oembed.oembed("tiktok", "https://www.tiktok.com/@tiktok/video/6829267836783971589")
    hard.append(_line("oEmbed TikTok", bool(tk),
                      "needs stealth/proxy last-mile (TikTok drops non-browser)"))

    vid = frontends.invidious_video("dQw4w9WgXcQ")
    hard.append(_line("Invidious (public instance)", bool(vid),
                      "public instances flaky -> self-host for production"))

    print("\n=== CHEAP STACK LIVE VERIFICATION ===")
    print("\n-- FREE CORE (unblockable, no auth, must pass) --")
    for _, msg in core:
        print(msg)
    print("\n-- HARD PLATFORMS (informational: confirm where last-mile begins) --")
    for _, msg in hard:
        print(msg)

    core_ok = all(ok for ok, _ in core)
    passed = sum(1 for ok, _ in core if ok)
    print(f"\nFREE CORE: {passed}/{len(core)} verified live (no proxy, no API key).")
    print(f"OVERALL: {'PASS' if core_ok else 'FAIL'} "
          f"(hard-platform tier is informational, needs paid/self-host last-mile)\n")
    return 0 if core_ok else 1


if __name__ == "__main__":
    sys.exit(run())
