"""Phase 2 — natural language → QueryPlan → the same fan-out.

Turns "top 50 posts on TSLA in the last 10 minutes" or "bad posts about Windlass" into a
TRANSPARENT, editable plan (returned to the user — no black box, per the design), then the
executor runs the existing per-source fan-out and applies deterministic filters:
  - window_minutes : keep only items newer than N minutes ("last 10 mins")
  - sentiment      : keep only negative/harmful items ("bad", "harmful") — lexicon PROXY, honest
  - sort           : recency | engagement | relevance
  - top_n          : how many to keep
  - sources        : all, or a subset ("posts"→social, "news"→news sources, "tweets"→twitter)

A rule parser (always free, no key) handles the common intents; if GROQ_API_KEY is set the
LLM refines it. The plan is always shown so the interpretation is auditable.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

SOCIAL = ["reddit", "twitter", "tiktok", "youtube", "telegram", "instagram", "wechat"]
NEWS = ["news", "news-bing", "web", "gdelt"]

_TIME = re.compile(r"(?:last|past|within|in\s+the\s+last)\s+(\d+)\s*(minute|min|hour|hr|day|week)s?", re.I)
_TOPN = re.compile(r"top\s+(\d+)", re.I)
_UNIT_MIN = {"minute": 1, "min": 1, "hour": 60, "hr": 60, "day": 1440, "week": 10080}
_NEG_WORDS = ("bad", "harmful", "negative", "toxic", "hostile", "abusive", "hate",
              "criticism", "controvers", "outrage", "slander", "defam", "attack")
_SOCIAL_HINT = ("post", "posts", "tweet", "tweets", "comment", "social", "reel", "story")
_NEWS_HINT = ("news", "article", "articles", "coverage", "headline", "press")
_TWEET_HINT = ("tweet", "tweets", "twitter", "x.com")
# words that are intent/filter noise, not part of the entity being searched
_STRIP = {
    "give", "me", "show", "all", "the", "a", "an", "find", "get", "fetch", "on", "about",
    "of", "for", "in", "to", "related", "regarding", "any", "some", "me", "please",
    "last", "past", "within", "recent", "latest", "newest", "new", "old",
    "top", "most", "best", "trending", "viral",
    "post", "posts", "tweet", "tweets", "comment", "comments", "content", "news", "article",
    "articles", "coverage", "headline", "headlines", "reel", "reels", "story", "stories",
    "bad", "harmful", "negative", "toxic", "hostile", "abusive", "hate", "hateful",
    "minute", "minutes", "min", "mins", "hour", "hours", "hr", "hrs", "day", "days", "week", "weeks",
    "and", "with", "from", "data", "things",
}


@dataclass
class QueryPlan:
    raw: str
    query: str
    top_n: int = 10
    sort: str = "relevance"          # relevance | recency | engagement
    window_minutes: int | None = None
    sentiment: str | None = None     # None | "negative"
    sources: list[str] = field(default_factory=list)   # empty = all
    lens: dict | None = None
    parser: str = "rules"
    interpretation: str = ""


def _clean_query(s: str) -> str:
    toks = re.findall(r"[A-Za-z0-9$#@_.À-￿]+", s)
    keep = [t for t in toks if t.lower() not in _STRIP and not t.isdigit()]
    return " ".join(keep).strip()


def rule_parse(nl: str) -> QueryPlan:
    s = (nl or "").strip()
    p = QueryPlan(raw=nl, query=s)
    low = s.lower()

    m = _TIME.search(s)
    if m:
        p.window_minutes = int(m.group(1)) * _UNIT_MIN[m.group(2).lower()]
        p.sort = "recency"

    m = _TOPN.search(s)
    if m:
        p.top_n = min(int(m.group(1)), 50)
        p.sort = "engagement"
    elif re.search(r"\btop\b|\bmost\b|\bviral\b|\btrending\b", low):
        p.sort = "engagement"
        p.top_n = 25
    if p.sort == "relevance" and re.search(r"latest|recent|newest|\bnew\b|\blast\b", low):
        p.sort = "recency"

    if any(w in low for w in _NEG_WORDS):
        p.sentiment = "negative"

    if any(w in low for w in _TWEET_HINT):
        p.sources = ["twitter"]
    elif any(w in low for w in _SOCIAL_HINT):
        p.sources = list(SOCIAL)
    elif any(w in low for w in _NEWS_HINT):
        p.sources = list(NEWS)

    p.query = _clean_query(s) or s
    p.parser = "rules"
    p.interpretation = _describe(p)
    return p


def _describe(p: QueryPlan) -> str:
    bits = [f'search "{p.query}"']
    bits.append("across " + (", ".join(p.sources) if p.sources else "all sources"))
    if p.sentiment == "negative":
        bits.append("keep only negative/harmful")
    if p.window_minutes:
        bits.append(f"posted in the last {p.window_minutes} min")
    bits.append(f"sort by {p.sort}, top {p.top_n} per source")
    return " · ".join(bits)


# ── filters applied to fetched items ─────────────────────────────────────────
_DATE_FIELDS = ("posted_at", "published", "date", "pubDate")
_DFMT = ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%a, %d %b %Y %H:%M:%S %z",
         "%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%d")
_NEG_LEX = {"corrupt", "scam", "fraud", "fail", "failure", "loss", "crash", "collapse", "worst",
            "terrible", "awful", "hate", "disaster", "shame", "fake", "liar", "lie", "attack",
            "kill", "dead", "war", "threat", "danger", "boycott", "protest", "anger", "angry",
            "outrage", "abuse", "toxic", "propaganda", "traitor", "coward", "defeat", "weak",
            "dump", "sell", "bearish", "plunge", "tank", "fell", "drop", "sink", "warning", "risk"}
_ENG_FIELDS = ("views", "likes", "upvotes", "comment_count", "shares", "cited_by_count")


def _age_min(it: dict) -> float | None:
    for f in _DATE_FIELDS:
        v = it.get(f)
        if not v:
            continue
        s = str(v).strip().replace("Z", "+0000")
        for fmt in _DFMT:
            try:
                d = datetime.strptime(s[:31], fmt)
                if d.tzinfo is None:
                    d = d.replace(tzinfo=timezone.utc)
                return max(0.0, (datetime.now(timezone.utc) - d).total_seconds() / 60)
            except ValueError:
                continue
    return None


def _engagement(it: dict) -> float:
    return float(sum(float(it.get(f) or 0) for f in _ENG_FIELDS))


def _is_negative(it: dict) -> bool:
    if float(it.get("toxicity") or 0) >= 0.5 or it.get("weaponization_signals"):
        return True
    blob = " ".join(str(it.get(f, "")) for f in
                    ("title", "post_text", "text", "snippet", "description")).lower()
    return any(w in blob for w in _NEG_LEX)


def apply_plan(p: QueryPlan, items: list[dict]) -> list[dict]:
    out = list(items)
    if p.window_minutes is not None:
        out = [it for it in out if (a := _age_min(it)) is not None and a <= p.window_minutes]
    if p.sentiment == "negative":
        out = [it for it in out if _is_negative(it)]
    if p.sort == "recency":
        out.sort(key=lambda it: (_age_min(it) if _age_min(it) is not None else 1e12))
    elif p.sort == "engagement":
        out.sort(key=_engagement, reverse=True)
    return out[: p.top_n]


def to_dict(p: QueryPlan) -> dict:
    return asdict(p)
