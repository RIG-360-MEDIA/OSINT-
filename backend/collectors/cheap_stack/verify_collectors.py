"""End-to-end verification of the real collectors (normalized interface).

Runs each Collector.profile() against a live public handle and prints the
normalized ProfileResult. Proves the swap-able-method framework works end to end.

    python -m backend.collectors.cheap_stack.verify_collectors
"""
from __future__ import annotations

import sys

from .base import Egress
from .instagram import InstagramCollector
from .tiktok import TikTokCollector
from .wechat import WeChatCollector


def _show(r) -> bool:
    tag = "PASS" if r.ok else "FAIL"
    if r.ok:
        detail = (f"name={r.display_name!r} followers={r.followers} "
                  f"posts={r.posts_count} verified={r.verified} via={r.method}")
    else:
        detail = f"error={r.error} via={r.method}"
    print(f"[{tag}] {r.platform:<10} @{r.handle:<16} {detail}")
    return r.ok


def run() -> int:
    try:  # Windows consoles default to cp1252 and choke on CJK output
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    egress = Egress()  # direct; on Hetzner pass Egress(proxies={...}, label="residential")
    print("\n=== END-TO-END COLLECTOR VERIFICATION (normalized interface) ===")
    print(f"egress = {egress.label}\n")

    checks = []
    ig = InstagramCollector()
    print(f"instagram methods: {ig.method_names}")
    checks.append(_show(ig.profile("instagram", egress)))

    tt = TikTokCollector()
    print(f"tiktok methods:    {tt.method_names}")
    checks.append(_show(tt.profile("tiktok", egress)))

    wc = WeChatCollector()
    print(f"wechat methods:    {wc.method_names}")
    wc_ok = _show(wc.profile("腾讯", egress))  # Tencent official account
    # WeChat is best-effort (Sogou captcha) — report but don't gate the run on it.

    passed = sum(1 for c in checks if c)
    print(f"\nCORE (IG+TikTok): {passed}/{len(checks)} PASS  |  WeChat: "
          f"{'PASS' if wc_ok else 'PARTIAL/FAIL (Sogou anti-crawl — expected)'}")
    print("Note: verified on this IP. Instagram will 403 from datacenter IPs — "
          "pass Egress(proxies=...residential...) on Hetzner.\n")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(run())
