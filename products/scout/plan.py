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
    queries: list[str] = field(default_factory=list)   # >1 for co-occurrence expansion
    topic: str = ""
    anchor: str = ""                 # the "perspective" entity, if any
    top_n: int = 10
    sort: str = "relevance"          # relevance | recency | engagement
    window_minutes: int | None = None
    sentiment: str | None = None     # None | "negative"
    sources: list[str] = field(default_factory=list)   # empty = all
    lens: dict | None = None
    parser: str = "rules"
    interpretation: str = ""


# "TOPIC from ANCHOR's perspective" and friends → (topic, anchor). Order flag: "ta"=topic,anchor.
_PERSP = [
    (re.compile(r"^(.*?)\s+(?:from|in|through)\s+(.*?)(?:'s|s)?\s+(?:perspective|point of view|pov|viewpoint|view|lens|eyes|angle|standpoint)\b", re.I), "ta"),
    (re.compile(r"^(.*?)\s+(?:from|in)\s+(?:the\s+)?perspective\s+of\s+(.*)$", re.I), "ta"),
    (re.compile(r"^(.*?)(?:'s|s)?\s+(?:take|view|opinion|reaction|response|stance|angle)\s+on\s+(.*)$", re.I), "at"),
    (re.compile(r"^how\s+(?:does|do|is|are)\s+(.*?)\s+(?:see|seeing|view|viewing|react\w*|respond\w*)\s+(?:to\s+)?(.*)$", re.I), "at"),
]
_LEAD = re.compile(r"^(?:all|the|any|give me|show me|find|get|posts?|content|news|tweets?|about|on|of)\s+", re.I)


def _trim(s: str) -> str:
    s = s.strip().strip("?.!,")
    while True:
        t = _LEAD.sub("", s)
        if t == s:
            return t.strip()
        s = t


def _split_perspective(s: str):
    for rx, order in _PERSP:
        m = rx.search(s)
        if m:
            g1, g2 = _trim(m.group(1)), _trim(m.group(2))
            topic, anchor = (g1, g2) if order == "ta" else (g2, g1)
            if topic and anchor and topic.lower() != anchor.lower():
                return topic, anchor
    return None


def _expand(topic: str, anchor: str) -> list[str]:
    """Co-occurrence queries: force topic AND anchor to appear together, in a few framings."""
    t, a = topic.strip(), anchor.strip()
    cands = [f"{t} {a}", f"{a} on {t}", f"{a} reaction {t}", f"{a} {t} view"]
    seen, out = set(), []
    for q in cands:
        q = " ".join(q.split())
        if q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out[:4]


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
    persp = _split_perspective(s)
    if persp:
        p.topic, p.anchor = persp
        p.queries = _expand(p.topic, p.anchor)
        p.query = p.queries[0]
    else:
        p.queries = [p.query]
    p.parser = "rules"
    p.interpretation = _describe(p)
    return p


def _describe(p: QueryPlan) -> str:
    if p.anchor:
        bits = [f'"{p.topic}" through the lens of "{p.anchor}"',
                "co-occurrence queries → " + " | ".join(p.queries)]
    else:
        bits = [f'search "{p.query}"']
    bits.append("across " + (", ".join(p.sources) if p.sources else "all sources"))
    if p.sentiment == "negative":
        bits.append("keep only negative/harmful")
    if p.window_minutes:
        bits.append(f"posted in the last {p.window_minutes} min")
    bits.append(f"rank by {'co-occurrence' if p.anchor else p.sort}, top {p.top_n} per source")
    return " · ".join(bits)


# ── filters applied to fetched items ─────────────────────────────────────────
_DATE_FIELDS = ("posted_at", "published", "date", "pubDate")
_DFMT = ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%a, %d %b %Y %H:%M:%S %z",
         "%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%d")
# Strong, unambiguous negativity/hostility stems — matched at a WORD BOUNDARY (not substring,
# so "war" won't match "forward" and "sell" won't match "reseller"). A keyword PROXY for
# "bad/harmful", not verified sentiment — honest floor; upgrade path is an LLM judge.
_NEG_LEX = ("corrupt", "scam", "fraud", "fail", "crash", "collaps", "worst", "terrible", "awful",
            "hate", "disaster", "shame", "fake", "liar", "traitor", "coward", "boycott", "outrage",
            "abuse", "toxic", "propaganda", "threat", "atrocit", "attack", "kill", "massacre",
            "criticis", "criticiz", "slam", "blast", "condemn", "controvers", "defam", "protest",
            "angry", "anger", "disgrace", "scandal", "incompeten", "betray", "enemy", "brutal",
            "genocide", "oppress", "violat", "coverup", "cover-up", "lies", "hypocris")
_NEG_RE = re.compile(r"\b(" + "|".join(_NEG_LEX) + r")", re.I)
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
                    ("title", "post_text", "text", "snippet", "description"))
    return bool(_NEG_RE.search(blob))


def _toks(s: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]{3,}", (s or "").lower())]


def _cooccur(it: dict, ttoks: list[str], atoks: list[str]) -> int:
    blob = " ".join(str(it.get(f, "")) for f in
                    ("title", "post_text", "text", "snippet", "description")).lower()
    return (1 if any(t in blob for t in ttoks) else 0) + (1 if any(a in blob for a in atoks) else 0)


def apply_plan(p: QueryPlan, items: list[dict]) -> list[dict]:
    out = list(items)
    if p.window_minutes is not None:
        out = [it for it in out if (a := _age_min(it)) is not None and a <= p.window_minutes]
    if p.sentiment == "negative":
        out = [it for it in out if _is_negative(it)]
    if p.anchor:                                        # perspective → co-occurrence first, then fresh
        tt, at = _toks(p.topic), _toks(p.anchor)
        out.sort(key=lambda it: (-_cooccur(it, tt, at),
                                 _age_min(it) if _age_min(it) is not None else 1e12))
    elif p.sort == "recency":
        out.sort(key=lambda it: (_age_min(it) if _age_min(it) is not None else 1e12))
    elif p.sort == "engagement":
        out.sort(key=_engagement, reverse=True)
    return out[: p.top_n]


def to_dict(p: QueryPlan) -> dict:
    return asdict(p)
