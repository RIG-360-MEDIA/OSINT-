"""Goldmine + deductions from a keyword's cross-platform scrape.

Pure, rule-based synthesis (no LLM — the pool is capacity-limited). Given the
per-platform collector results, surface the goldmine items (highest-signal
posts / full content) and a layered set of analytical deductions:

  • where the signal concentrates (platform breakdown, loudest voices)
  • how fast it's moving (tempo + velocity: rising / steady / fading)
  • who is driving it (top voices, verified/official share)
  • what is being said (cross-platform themes, narrative phrases, hashtags)
  • quantified claims worth verifying (numbers + units pulled from text)
  • the audience footprint (aggregate reach) and language framing

Every deduction is derived from the posts actually returned — no fabrication.
Sections degrade gracefully to empty when a signal isn't present.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

_NOW = datetime.now(timezone.utc)
_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")
_HASHTAG_RE = re.compile(r"#(\w{2,40})", re.UNICODE)
_MENTION_RE = re.compile(r"@(\w{2,40})")
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|\n+")
# A number (optionally grouped/decimal) sitting next to a scale word or a
# conflict/econ unit — the kind of claim an analyst would want to verify.
_CLAIM_RE = re.compile(
    r"(?:[₹$€£]\s?\d[\d,.]*|\d[\d,.]*\s?%|\d[\d,.]*\s?"
    r"(?:million|billion|trillion|crore|lakh|thousand|k\b|bn\b|"
    r"km|kilomet\w*|mile|miles|tonnes?|tons?|"
    r"killed|dead|injured|wounded|casualt\w*|martyr\w*|troops?|soldiers?|"
    r"missiles?|drones?|jets?|fighters?|ships?|submarines?|aircraft|tanks?|"
    r"votes?|seats?|arrests?|detained))",
    re.IGNORECASE,
)
_STOP = {
    "the", "and", "for", "with", "that", "this", "have", "has", "was", "are",
    "https", "http", "www", "com", "amp", "you", "your", "will", "not", "but",
    "all", "new", "one", "out", "from", "its", "they", "their", "our", "his",
    "her", "video", "watch", "news", "via", "who", "how", "why", "what", "when",
    "into", "over", "after", "amid", "says", "said", "were", "been", "than",
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
            q["_dt"] = _parse_ts(p.get("posted_at"))
            out.append(q)
    return out


def _fmt_int(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(int(n))


# ── analytical sub-signals ──────────────────────────────────────────────────

def _platform_breakdown(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-platform post count + engagement share — where the signal lives."""
    by: dict[str, dict[str, int]] = {}
    for p in posts:
        b = by.setdefault(p["_platform"], {"posts": 0, "engagement": 0})
        b["posts"] += 1
        b["engagement"] += p["_engagement"]
    tot_e = sum(b["engagement"] for b in by.values()) or 1
    tot_p = len(posts) or 1
    rows = [
        {"platform": k, "posts": v["posts"], "engagement": v["engagement"],
         "post_share": round(100 * v["posts"] / tot_p),
         "eng_share": round(100 * v["engagement"] / tot_e)}
        for k, v in by.items()
    ]
    return sorted(rows, key=lambda r: (-r["engagement"], -r["posts"]))


def _top_voices(posts: list[dict[str, Any]], n: int = 5) -> list[dict[str, Any]]:
    """Accounts driving the conversation, ranked by total engagement then volume."""
    by: dict[tuple[str, str], dict[str, Any]] = {}
    for p in posts:
        author = (p.get("author_username") or "").strip()
        if not author:
            continue
        key = (p["_platform"], author)
        v = by.setdefault(key, {"platform": p["_platform"], "author": author,
                                "posts": 0, "engagement": 0, "verified": False})
        v["posts"] += 1
        v["engagement"] += p["_engagement"]
        v["verified"] = v["verified"] or bool(p.get("verified"))
    return sorted(by.values(),
                  key=lambda v: (-v["engagement"], -v["posts"]))[:n]


def _velocity(posts: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare the last 24h vs the prior 24h → rising / steady / fading."""
    last24 = prev24 = 0
    for p in posts:
        d = p.get("_dt")
        if not d:
            continue
        age_h = (_NOW - d).total_seconds() / 3600
        if age_h < 24:
            last24 += 1
        elif age_h < 48:
            prev24 += 1
    if last24 + prev24 < 3:
        trend = "insufficient"
    elif last24 >= max(prev24 * 1.5, prev24 + 2):
        trend = "rising"
    elif last24 * 1.5 < prev24:
        trend = "fading"
    else:
        trend = "steady"
    return {"last_24h": last24, "prev_24h": prev24, "trend": trend}


def _signals(posts: list[dict[str, Any]]) -> dict[str, list]:
    """Top hashtags and @mentions across the corpus — the entities in play."""
    tags: Counter = Counter()
    mentions: Counter = Counter()
    for p in posts:
        txt = p.get("post_text") or ""
        tags.update(t.lower() for t in _HASHTAG_RE.findall(txt))
        mentions.update(m.lower() for m in _MENTION_RE.findall(txt))
    return {
        "hashtags": [{"tag": t, "n": c} for t, c in tags.most_common(8)],
        "mentions": [{"handle": m, "n": c} for m, c in mentions.most_common(6)],
    }


def _numeric_claims(posts: list[dict[str, Any]], kw: str, n: int = 5) -> list[dict]:
    """Sentences carrying a quantified claim (number + unit) — verify targets."""
    seen: set[str] = set()
    out: list[dict] = []
    # engagement-first so the most-amplified claims surface
    for p in sorted(posts, key=lambda x: -x["_engagement"]):
        txt = (p.get("post_text") or "").strip()
        if not txt:
            continue
        for sent in _SENT_SPLIT_RE.split(txt):
            sent = sent.strip()
            if not (10 < len(sent) < 240) or not _CLAIM_RE.search(sent):
                continue
            norm = re.sub(r"\s+", " ", sent.lower())
            if norm in seen:
                continue
            seen.add(norm)
            out.append({"claim": sent[:240], "platform": p["_platform"],
                        "author": p.get("author_username"), "url": p.get("post_url")})
            if len(out) >= n:
                return out
    return out


def _language_mix(posts: list[dict[str, Any]]) -> dict[str, Any]:
    """Rough script distribution over post text — reveals a regional/foreign angle."""
    buckets = {"latin": 0, "devanagari": 0, "cjk": 0, "arabic": 0, "cyrillic": 0}
    total = 0
    for p in posts:
        for ch in (p.get("post_text") or ""):
            o = ord(ch)
            if ch.isalpha():
                total += 1
                if o < 0x250:
                    buckets["latin"] += 1
                elif 0x900 <= o <= 0x97F:
                    buckets["devanagari"] += 1
                elif 0x4E00 <= o <= 0x9FFF or 0x3040 <= o <= 0x30FF:
                    buckets["cjk"] += 1
                elif 0x600 <= o <= 0x6FF:
                    buckets["arabic"] += 1
                elif 0x400 <= o <= 0x4FF:
                    buckets["cyrillic"] += 1
    if not total:
        return {"total_chars": 0, "shares": {}, "non_latin_pct": 0}
    shares = {k: round(100 * v / total) for k, v in buckets.items() if v}
    return {"total_chars": total, "shares": shares,
            "non_latin_pct": round(100 * (total - buckets["latin"]) / total)}


def _media_richness(posts: list[dict[str, Any]]) -> dict[str, int]:
    total = len(posts) or 1
    video = sum(1 for p in posts if p.get("views") or p.get("duration")
                or p["_platform"] in ("youtube", "tiktok"))
    linked = sum(1 for p in posts if p.get("external_url"))
    verified = sum(1 for p in posts if p.get("verified"))
    return {"video_pct": round(100 * video / total),
            "linked_pct": round(100 * linked / total),
            "verified_pct": round(100 * verified / total)}


def _themes(posts: list[dict[str, Any]], kw_toks: set[str]) -> list[tuple[str, int]]:
    """Tokens that recur across ≥3 platforms — corroborated cross-platform themes."""
    tok_platforms: dict[str, set[str]] = {}
    for p in posts:
        seen = set(_TOKEN_RE.findall((p.get("post_text") or "").lower()))
        for t in seen:
            if t in kw_toks or t in _STOP or t.isdigit():
                continue
            tok_platforms.setdefault(t, set()).add(p["_platform"])
    return sorted(((t, len(pl)) for t, pl in tok_platforms.items() if len(pl) >= 3),
                  key=lambda x: (-x[1], x[0]))[:8]


def _narrative_phrases(posts: list[dict[str, Any]], kw_toks: set[str],
                       n: int = 6) -> list[str]:
    """Most common 2-word phrases (excluding the keyword) — the framing in words."""
    bigrams: Counter = Counter()
    for p in posts:
        toks = [t for t in _TOKEN_RE.findall((p.get("post_text") or "").lower())
                if t not in _STOP and not t.isdigit()]
        for a, b in zip(toks, toks[1:]):
            if a in kw_toks and b in kw_toks:
                continue
            bigrams[f"{a} {b}"] += 1
    return [ph for ph, c in bigrams.most_common(n) if c >= 2]


# ── main ────────────────────────────────────────────────────────────────────

def build_insights(keyword: str, results: dict[str, Any]) -> dict[str, Any]:
    posts = _all_posts(results)
    total = len(posts)
    platforms_hit = [p for p, r in results.items() if r.get("posts")]
    kw_toks = set(_TOKEN_RE.findall(keyword.lower()))

    dated = [p for p in posts if p.get("_dt")]
    fresh_48h = sum(1 for p in dated if (_NOW - p["_dt"]).total_seconds() < 48 * 3600)
    fresh_7d = sum(1 for p in dated if (_NOW - p["_dt"]).total_seconds() < 7 * 86400)

    breakdown = _platform_breakdown(posts)
    voices = _top_voices(posts)
    velocity = _velocity(posts)
    signals = _signals(posts)
    claims = _numeric_claims(posts, keyword)
    langs = _language_mix(posts)
    media = _media_richness(posts)
    themes = _themes(posts, kw_toks)
    phrases = _narrative_phrases(posts, kw_toks)

    reach_views = sum(int(p.get("views") or 0) for p in posts)
    reach_eng = sum(p["_engagement"] for p in posts)

    top_post = max(posts, key=lambda p: p["_engagement"], default=None)
    most_viewed = max((p for p in posts if p.get("views")),
                      key=lambda p: p.get("views") or 0, default=None)
    wechat_article = next(
        (p for p in posts if p["_platform"] == "wechat" and p.get("content")), None)

    # ── layered, human-readable deductions ───────────────────────────────
    d: list[str] = []
    d.append(f"Coverage: {total} posts across {len(platforms_hit)}/{len(results)} "
             f"platforms ({', '.join(platforms_hit) or 'none'}).")

    if breakdown:
        lead = breakdown[0]
        d.append(f"Signal concentrates on {lead['platform']} "
                 f"({lead['post_share']}% of posts, {lead['eng_share']}% of "
                 f"engagement); {'single-platform story' if len(breakdown) == 1 else f'{len(breakdown)} platforms carry it'}.")

    if dated:
        pct = round(100 * fresh_48h / len(dated))
        tempo = ("BREAKING — mostly last 48h" if pct >= 50
                 else "active — some fresh activity" if fresh_48h
                 else "historical — little recent activity")
        vtxt = {"rising": " and ACCELERATING (last 24h > prior 24h)",
                "fading": " but COOLING (last 24h < prior 24h)",
                "steady": " at a steady pace",
                "insufficient": ""}[velocity["trend"]]
        d.append(f"Tempo: {fresh_48h} in 48h, {fresh_7d} in 7d ({pct}% fresh) "
                 f"→ {tempo}{vtxt}.")

    if voices:
        vs = "; ".join(
            f"@{v['author']} ({v['platform']}, {v['posts']}p/"
            f"{_fmt_int(v['engagement'])} eng{', ✓' if v['verified'] else ''})"
            for v in voices[:3])
        d.append(f"Loudest voices: {vs}.")
        if media["verified_pct"] >= 40:
            d.append(f"Driven by established/verified accounts "
                     f"({media['verified_pct']}% verified) → official/media-led, "
                     f"not grassroots.")
        elif media["verified_pct"] <= 10:
            d.append(f"Largely unverified accounts "
                     f"({media['verified_pct']}% verified) → grassroots / UGC-led; "
                     f"corroborate before trusting.")

    if themes:
        d.append("Corroborated themes (≥3 platforms): "
                 + ", ".join(f"{t} ({n})" for t, n in themes) + ".")
    if phrases:
        d.append("Narrative framing (top phrases): " + ", ".join(phrases[:6]) + ".")

    if langs["non_latin_pct"] >= 15:
        parts = ", ".join(f"{k} {v}%" for k, v in sorted(
            langs["shares"].items(), key=lambda x: -x[1]) if k != "latin")
        d.append(f"Language: {langs['non_latin_pct']}% non-Latin script ({parts}) "
                 f"→ strong regional / foreign-language framing present.")

    if claims:
        d.append(f"Quantified claims to verify ({len(claims)}): "
                 + " | ".join(f"“{c['claim'][:90]}”" for c in claims[:3]) + ".")

    if signals["hashtags"]:
        d.append("Hashtag agenda: "
                 + ", ".join(f"#{h['tag']}" for h in signals["hashtags"][:6]) + ".")

    if reach_views or reach_eng:
        d.append(f"Footprint: ~{_fmt_int(reach_views)} views + "
                 f"{_fmt_int(reach_eng)} engagements visible across the sample.")

    if media["video_pct"] >= 50:
        d.append(f"Format-heavy: {media['video_pct']}% of items are video "
                 f"→ narrative is being carried visually, not in text.")

    if wechat_article:
        d.append("Differentiator: a Chinese-source WeChat Official-Account article "
                 "with full body is present (highest-differentiation OSINT).")

    def _slim(p: dict[str, Any] | None) -> dict[str, Any] | None:
        if not p:
            return None
        return {"platform": p["_platform"], "author": p.get("author_username"),
                "text": (p.get("post_text") or "")[:280], "url": p.get("post_url"),
                "engagement": p["_engagement"], "views": p.get("views"),
                "posted_at": p.get("posted_at")}

    return {
        "stats": {
            "total_posts": total, "platforms_hit": platforms_hit,
            "platform_count": len(platforms_hit),
            "fresh_48h": fresh_48h, "fresh_7d": fresh_7d,
            "reach_views": reach_views, "reach_engagement": reach_eng,
        },
        "themes": [{"term": t, "platforms": n} for t, n in themes],
        "narrative": phrases,
        "platform_breakdown": breakdown,
        "voices": voices,
        "velocity": velocity,
        "signals": signals,
        "claims": claims,
        "language_mix": langs,
        "media": media,
        "deductions": d,
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
