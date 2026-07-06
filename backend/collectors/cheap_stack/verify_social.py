"""Live per-platform social verification — honest PASS/PARTIAL/FAIL scorecard.

Each platform is tried with its best FREE (no-paid-proxy, no-paid-API) method.
Run:  python -m backend.collectors.cheap_stack.verify_social

Legend:
  PASS    = real structured data returned, free, no auth
  PARTIAL = page/endpoint reachable but needs parse or a free token/self-host
  FAIL    = blocked; needs paid proxy / stealth / paid API (last-mile)
"""
from __future__ import annotations

import json as _json
import sys
from urllib.parse import quote

from .browser_fetch import fetch
from . import oembed


def _row(platform: str, verdict: str, method: str, detail: str) -> tuple[str, str]:
    return verdict, f"[{verdict:<7}] {platform:<12} via {method:<22} {detail}"


def run() -> int:
    rows = []

    # YouTube — official oEmbed
    yt = oembed.oembed("youtube", "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    rows.append(_row("YouTube", "PASS" if yt else "FAIL", "oEmbed (official)",
                     f"title={ (yt or {}).get('title','-')[:32] }"))

    # Twitter/X — official publish oEmbed
    tw = oembed.oembed("twitter", "https://twitter.com/jack/status/20")
    rows.append(_row("Twitter/X", "PASS" if tw else "FAIL", "oEmbed (official)",
                     f"author={ (tw or {}).get('author_name','-') }"))

    # Reddit — free JSON endpoint via browser impersonation
    rd = fetch("https://www.reddit.com/r/worldnews/hot.json", params={"limit": "3"})
    rd_ok = False
    rd_detail = f"status={rd.status}"
    if rd.ok:
        try:
            n = len(rd.json.get("data", {}).get("children", []))
            rd_ok = n > 0
            rd_detail = f"posts={n}"
        except Exception:
            rd_detail = "unparseable"
    rows.append(_row("Reddit", "PASS" if rd_ok else ("PARTIAL" if rd.ok else "FAIL"),
                     "free .json + curl_cffi", rd_detail))

    # Telegram — public channel web preview (t.me/s/<channel>), no auth
    tg = fetch("https://t.me/s/durov")
    tg_ok = tg.ok and "tgme_widget_message" in tg.text
    tg_posts = tg.text.count("tgme_widget_message_text")
    rows.append(_row("Telegram", "PASS" if tg_ok else ("PARTIAL" if tg.ok else "FAIL"),
                     "t.me/s public preview", f"status={tg.status} posts~{tg_posts}"))

    # Instagram — public oEmbed (deprecated w/o token) then public page probe
    ig = fetch("https://www.instagram.com/instagram/", timeout=20)
    ig_has = ig.ok and ("og:description" in ig.text or "profilePage" in ig.text.lower())
    rows.append(_row("Instagram", "PARTIAL" if ig_has else "FAIL",
                     "public page + curl_cffi",
                     f"status={ig.status} og-meta={'yes' if ig_has else 'no'} (login-walled)"))

    # VK — public profile page via impersonation (API proper needs free token)
    vk = fetch("https://vk.com/durov", timeout=20)
    vk_ok = vk.ok and ("og:title" in vk.text or "profile" in vk.text.lower())
    rows.append(_row("VK", "PARTIAL" if vk_ok else "FAIL", "public page + curl_cffi",
                     f"status={vk.status} (proper: free official API token)"))

    # Facebook — public page probe (expected login wall)
    fb = fetch("https://www.facebook.com/nasa", timeout=20)
    fb_ok = fb.ok and "og:title" in fb.text
    rows.append(_row("Facebook", "PARTIAL" if fb_ok else "FAIL", "public page + curl_cffi",
                     f"status={fb.status} (mostly login-walled)"))

    # TikTok — official oEmbed (known to drop non-browser)
    tk = oembed.oembed("tiktok", "https://www.tiktok.com/@tiktok/video/6829267836783971589")
    rows.append(_row("TikTok", "PASS" if tk else "FAIL", "oEmbed (official)",
                     "drops non-browser -> stealth/proxy last-mile"))

    # LinkedIn — no free path by design
    rows.append(_row("LinkedIn", "FAIL", "n/a (buy per-lookup)",
                     "no free path; paid API provider only"))

    print("\n=== SOCIAL PLATFORM LIVE SCORECARD (free methods only) ===")
    for _, msg in rows:
        print(msg)

    counts = {}
    for v, _ in rows:
        counts[v] = counts.get(v, 0) + 1
    summary = " ".join(f"{k}={counts[k]}" for k in ("PASS", "PARTIAL", "FAIL") if k in counts)
    print(f"\nSUMMARY: {summary}  (of {len(rows)} platforms)\n")
    return 0


if __name__ == "__main__":
    sys.exit(run())
