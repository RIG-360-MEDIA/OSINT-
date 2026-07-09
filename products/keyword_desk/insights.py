"""Goldmine + deductions from a keyword's cross-platform scrape.

Pure, rule-based synthesis (no LLM — the pool is capacity-limited). Given the
per-platform collector results, surface: the goldmine items (highest-signal
posts / full content) and deductions (recency, cross-platform themes, source
diversity, top sources).
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

_NOW = datetime.now(timezone.utc)
_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")
_STOP = {
    "the", "and", "for", "with", "that", "this", "から", "から",
    "https", "http", "www", "com", "amp", "you", "your", "are", "was",
    "has", "have", "will", "not", "but", "all", "new", "one", "out",
    "从", "video", "watch", "news", "via", "who", "how", "why", "what",
}


def _parse_ts(v: Any) -> datetime | None:
    if not v or not isinstance(v, str):
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _engagement(p: dict[str, Any]) -> int:
    """A cross-platform engagement score (views weighted down)."""
    return (
        int(p.get("upvotes") or 0)
        + int(p.get("likes") or 0)
        + int(p.get("comment_count") or 0) * 2
        + int(p.get("shares") or 0) * 3
        + int(p.get("views") or 0) // 200
    )


def _all_posts(results: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for platform, res in results.items():
        for p in res.get("posts", []):
            q = dict(p)
            q["_platform"] = platform
            q["_engagement"] = _engagement(p)
            out.append(q)
    return out


def build_insights(keyword: str, results: dict[str, Any]) -> dict[str, Any]:
    posts = _all_posts(results)
    total = len(posts)
    platforms_hit = [p for p, r in results.items() if r.get("posts")]

    # ── recency ──────────────────────────────────────────────────────────
    dated = [(_parse_ts(p.get("posted_at")), p) for p in posts]
    dated = [(d, p) for d, p in dated if d]
    fresh_48h = sum(1 for d, _ in dated if (_NOW - d).total_seconds() < 48 * 3600)
    fresh_7d = sum(1 for d, _ in dated if (_NOW - d).total_seconds() < 7 * 24 * 3600)

    # ── cross-platform themes: tokens appearing across >=3 platforms ─────
    kw_toks = set(_TOKEN_RE.findall(keyword.lower()))
    tok_platforms: dict[str, set[str]] = {}
    for p in posts:
        seen = set(_TOKEN_RE.findall((p.get("post_text") or "").lower()))
        for t in seen:
            if t in kw_toks or t in _STOP:
                continue
            tok_platforms.setdefault(t, set()).add(p["_platform"])
    themes = sorted(
        ((t, len(pl)) for t, pl in tok_platforms.items() if len(pl) >= 3),
        key=lambda x: (-x[1], x[0]),
    )[:8]

    # ── goldmine picks ───────────────────────────────────────────────────
    top_post = max(posts, key=lambda p: p["_engagement"], default=None)
    most_viewed = max(
        (p for p in posts if p.get("views")), key=lambda p: p.get("views") or 0,
        default=None,
    )
    wechat_article = next(
        (p for p in posts if p["_platform"] == "wechat" and p.get("content")), None)

    # ── deductions (human-readable) ──────────────────────────────────────
    deductions: list[str] = []
    deductions.append(
        f"Coverage: {total} posts across {len(platforms_hit)}/{len(results)} platforms "
        f"({', '.join(platforms_hit) or 'none'})."
    )
    if dated:
        pct = round(100 * fresh_48h / len(dated))
        tempo = ("BREAKING — mostly last 48h" if pct >= 50
                 else "active — some fresh activity" if fresh_48h
                 else "historical — little recent activity")
        deductions.append(
            f"Tempo: {fresh_48h} posts in 48h, {fresh_7d} in 7d ({pct}% fresh) → {tempo}."
        )
    if themes:
        deductions.append(
            "Cross-platform themes (appear on ≥3 platforms): "
            + ", ".join(f"{t} ({n})" for t, n in themes) + "."
        )
    if top_post:
        deductions.append(
            f"Peak signal: {top_post['_platform']} @{top_post.get('author_username') or '?'} "
            f"— {top_post['_engagement']:,} engagement."
        )
    if wechat_article:
        deductions.append(
            "Differentiator: a Chinese-source WeChat Official-Account article with full "
            "body is present (highest-differentiation OSINT)."
        )

    def _slim(p: dict[str, Any] | None) -> dict[str, Any] | None:
        if not p:
            return None
        return {
            "platform": p["_platform"], "author": p.get("author_username"),
            "text": (p.get("post_text") or "")[:280], "url": p.get("post_url"),
            "engagement": p["_engagement"], "views": p.get("views"),
            "posted_at": p.get("posted_at"),
        }

    return {
        "stats": {
            "total_posts": total,
            "platforms_hit": platforms_hit,
            "platform_count": len(platforms_hit),
            "fresh_48h": fresh_48h, "fresh_7d": fresh_7d,
        },
        "themes": [{"term": t, "platforms": n} for t, n in themes],
        "deductions": deductions,
        "goldmine": {
            "top_post": _slim(top_post),
            "most_viewed": _slim(most_viewed),
            "wechat_article": ({
                "account": wechat_article.get("account"),
                "title": wechat_article.get("title"),
                "content": (wechat_article.get("content") or "")[:1500],
                "url": wechat_article.get("post_url"),
                "posted_at": wechat_article.get("posted_at"),
            } if wechat_article else None),
        },
    }
