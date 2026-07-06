"""WeChat collector — public Official Accounts via Sogou Weixin (the OSINT route).

WeChat has no open API and personal accounts are app-only. The standard OSINT
path is Sogou Weixin (weixin.sogou.com), which indexes public Official Accounts
and their articles. Anti-crawl is heavy (captcha/cookie gates) so this is a
best-effort method — often PARTIAL. Alt routes worth adding as methods later:
wechat2rss, wechat_db_parser (local client DB).
"""
from __future__ import annotations

import re
from html import unescape
from typing import Optional

from curl_cffi import requests as cffi_requests

from .base import Collector, Egress, Method, ProfileResult

# Account result box in Sogou Weixin (type=1) HTML.
_NAME_RE = re.compile(r'<p class="tit">\s*<a[^>]*>(.*?)</a>', re.DOTALL)
_WXID_RE = re.compile(r'<label[^>]*>(?:微信号|WeChat ID)[:：]?\s*</label>\s*([A-Za-z0-9_\-]+)')
_STRIP_TAGS = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return unescape(_STRIP_TAGS.sub("", text)).strip()


class SogouWeixinMethod:
    """Search public Official Accounts by name via Sogou Weixin."""

    name = "sogou_weixin"

    def fetch_profile(self, handle: str, egress: Egress) -> Optional[ProfileResult]:
        # Sogou returns an empty shell until it has session cookies (SUV/SNUID).
        # Prime them by visiting the homepage first, then search on the same session.
        try:
            session = cffi_requests.Session(impersonate="chrome")
            session.get("https://weixin.sogou.com/", timeout=20,
                        proxies=egress.proxies)
            resp = session.get(
                "https://weixin.sogou.com/weixin",
                params={"type": "1", "query": handle, "ie": "utf8"},
                timeout=25, proxies=egress.proxies,
            )
        except Exception as exc:
            return ProfileResult(platform="wechat", handle=handle, ok=False,
                                 method=self.name, error=f"{type(exc).__name__}: {exc}")

        text = resp.text
        if resp.status_code >= 400:
            return ProfileResult(platform="wechat", handle=handle, ok=False,
                                 method=self.name, error=f"http {resp.status_code}")
        if "antispider" in text or "请输入验证码" in text or "验证码" in text:
            return ProfileResult(platform="wechat", handle=handle, ok=False,
                                 method=self.name,
                                 error="sogou captcha wall (needs aged cookie/residential)")

        name_m = _NAME_RE.search(text)
        if not name_m:
            return ProfileResult(platform="wechat", handle=handle, ok=False,
                                 method=self.name, error="no account results")
        wxid_m = _WXID_RE.search(text)
        return ProfileResult(
            platform="wechat",
            handle=(wxid_m.group(1) if wxid_m else handle),
            ok=True,
            method=self.name,
            display_name=_clean(name_m.group(1)),
            extra={
                "wechat_id": wxid_m.group(1) if wxid_m else None,
                "query": handle,
                "note": "public Official Account (personal accounts are app-only)",
            },
        )


class WeChatCollector(Collector):
    platform = "wechat"

    def __init__(self, methods: Optional[list[Method]] = None):
        super().__init__(methods or [SogouWeixinMethod()])
