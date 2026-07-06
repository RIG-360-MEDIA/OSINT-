"""Live probe of extra free methods for the HARD platforms.

Tests multiple techniques per platform and prints what actually returns data.
Run: python -m backend.collectors.cheap_stack.verify_hard

Honest verdicts:
  PASS    = structured data returned free/no-login
  PARTIAL = reachable / partial data or needs a free token
  FAIL    = blocked -> paid proxy / stealth / paid API
"""
from __future__ import annotations

import json as _json
import sys

from .browser_fetch import fetch

# Instagram public web app id (constant). Wrong value -> 403.
IG_APP_ID = "936619743392459"


def _v(ok: bool, partial: bool = False) -> str:
    return "PASS" if ok else ("PARTIAL" if partial else "FAIL")


def _p(platform: str, method: str, verdict: str, detail: str):
    print(f"[{verdict:<7}] {platform:<11} {method:<32} {detail}")


def instagram():
    # Method A: web_profile_info API with x-ig-app-id header
    r = fetch(
        "https://www.instagram.com/api/v1/users/web_profile_info/?username=instagram",
        headers={"x-ig-app-id": IG_APP_ID, "Accept": "application/json"},
        timeout=20,
    )
    okA = False
    detA = f"status={r.status}"
    if r.ok:
        try:
            u = r.json.get("data", {}).get("user", {})
            followers = u.get("edge_followed_by", {}).get("count")
            okA = followers is not None
            detA = f"followers={followers} posts={u.get('edge_owner_to_timeline_media',{}).get('count')}"
        except Exception:
            detA = "unparseable json"
    _p("Instagram", "web_profile_info + x-ig-app-id", _v(okA, r.ok), detA)

    # Method B: third-party public viewer (imginn)
    r2 = fetch("https://imginn.com/instagram/", timeout=20)
    okB = r2.ok and ("post" in r2.text.lower() or "follower" in r2.text.lower())
    _p("Instagram", "3rd-party viewer (imginn)", _v(False, okB), f"status={r2.status}")


def tiktok():
    # Method A: parse embedded __UNIVERSAL_DATA_FOR_REHYDRATION__ JSON from profile HTML
    r = fetch("https://www.tiktok.com/@tiktok", timeout=25)
    has = r.ok and "__UNIVERSAL_DATA_FOR_REHYDRATION__" in r.text
    _p("TikTok", "HTML UNIVERSAL_DATA blob", _v(False, has),
       f"status={r.status} blob={'yes' if has else 'no'}")

    # Method B: third-party free API (tikwm)
    r2 = fetch("https://www.tikwm.com/api/user/info", params={"unique_id": "tiktok"}, timeout=25)
    okB = False
    detB = f"status={r2.status}"
    if r2.ok:
        try:
            d = r2.json
            okB = str(d.get("code")) == "0"
            uid = d.get("data", {}).get("user", {}).get("uniqueId")
            detB = f"code={d.get('code')} user={uid}"
        except Exception:
            detB = "unparseable"
    _p("TikTok", "3rd-party API (tikwm)", _v(okB, r2.ok), detB)


def vk():
    # Public page og-meta (proper path = free official API token)
    r = fetch("https://vk.com/durov", timeout=20)
    has = r.ok and "og:title" in r.text
    _p("VK", "public page og-meta", _v(False, has),
       f"status={r.status} (proper: free official API token, api.vk.com)")


def wechat():
    # Sogou Weixin public-account search (the standard WeChat OSINT route)
    r = fetch("https://weixin.sogou.com/weixin", params={"type": "1", "query": "腾讯"}, timeout=25)
    has = r.ok and ("weixin" in r.text.lower() or "account" in r.text.lower() or "微信" in r.text)
    _p("WeChat", "Sogou Weixin account search", _v(False, has),
       f"status={r.status} (public accounts only; anti-crawl heavy)")


def facebook():
    # mbasic is the lightweight, less-JS surface
    r = fetch("https://mbasic.facebook.com/nasa", timeout=20)
    has = r.ok and ("NASA" in r.text or "og:title" in r.text)
    _p("Facebook", "mbasic.facebook.com public", _v(False, has),
       f"status={r.status} (login-wall varies)")


def run() -> int:
    print("\n=== HARD-PLATFORM EXTRA-METHOD LIVE PROBE (free only) ===")
    for fn in (instagram, tiktok, vk, wechat, facebook):
        try:
            fn()
        except Exception as exc:
            _p(fn.__name__.title(), "(probe error)", "FAIL", f"{type(exc).__name__}: {exc}")
    print("\n(PARTIAL = reachable/needs-parse-or-free-token; PASS = data in hand; FAIL = last-mile)\n")
    return 0


if __name__ == "__main__":
    sys.exit(run())
