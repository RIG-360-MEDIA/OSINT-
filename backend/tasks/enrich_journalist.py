"""enrich_journalist.py — periodic celery task to extract journalist name.

Runs every 5 minutes via beat schedule. Picks up substrate-ok articles
where `author_name IS NULL` (never tried) and runs the same extractor
the backfill script uses. Writes:
  - the extracted name → `articles.author_name`
  - empty string '' on miss (so we don't retry the same article)

No LLM tokens. Stage 1 (byline regex) is instant; Stage 2 (HTML re-fetch)
makes 1 HTTP call per article, throttled by the celery worker's
concurrency.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db

logger = logging.getLogger(__name__)

# ── Inline the extractor's blocklists (avoids cross-module imports) ──
PUBLISHER_TOKENS = {
    "today", "news", "bureau", "desk", "updated", "follow", "twitter", "instagram",
    "facebook", "team", "editor", "reporter", "correspondent", "staff", "web",
    "online", "agency", "service", "feed", "feeds", "network", "media", "newsroom",
    "wire", "agencies", "tv", "channel", "post", "times", "express", "tribune",
    "guardian", "hindu", "indianexpress", "ie", "pti", "ani", "ians", "ant",
    "ndtv", "ap", "afp", "reuters", "bloomberg", "iht", "fp", "scroll",
    "minute", "min", "minutes", "hours", "ago", "live", "blog", "bot",
    "automated", "agency", "report", "reports", "exclusive", "special",
    "syndication", "syndicated", "velugu", "trust", "author", "about",
    "telugu", "hindi", "english", "kannada", "tamil", "malayalam", "marathi",
    "bengali", "gujarati", "punjabi", "urdu",
}

KNOWN_PUBLISHER_PHRASES = {
    "v6 velugu", "daily trust", "press trust", "press trust of india",
    "about the author", "about the author livemint", "the author",
    "namasthe telangana", "telangana today", "nt news telugu",
    "hindu business line", "hindu businessline", "the hindu bureau",
    "bl chennai bureau", "bl mumbai bureau", "bl delhi bureau",
    "mint industry", "economic times", "indian express", "the indian express",
    "livemint", "live mint", "news desk", "web desk", "online desk",
    "by ians", "by pti", "by ani", "by reuters", "by afp", "by ap",
    "press release", "staff reporter", "staff correspondent",
    "special correspondent", "our correspondent", "our bureau",
    "csr journal", "the csr journal", "joy online",
    "this day", "this day nigeria",
    "dc correspondent", "ht news desk", "ht correspondent", "et bureau",
    "et online", "et markets", "agencies", "wire services",
    "the hindu", "hindu net desk", "the wire staff",
    "moneycontrol news", "tnn", "agence france-presse",
    "abp news bureau", "india tv news desk", "news18 india",
    "read more", "share this", "twitter facebook",
    "published by", "please enter your name here", "enter your name",
    "your name", "your email", "leave a comment", "leave a reply",
}

PERSON_NAME_RE = re.compile(
    r"^(?:by\s+|story\s+by\s+|written\s+by\s+|opinion\s+by\s+|reported\s+by\s+)?"
    r"(?P<name>[A-Z][a-zA-Z\.\'\-]+(?:\s+[A-Z][a-zA-Z\.\'\-]+){1,3})"
    r"(?:[,|;]|\s+for\s+|\s+\(|$)",
    re.IGNORECASE,
)


def _normalize_candidate(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^(?:by|story\s+by|written\s+by|reported\s+by|opinion\s+by)\s+",
               "", s, flags=re.IGNORECASE).strip()
    for sep in [",", ";", "|", "(", " - ", " — "]:
        if sep in s:
            s = s.split(sep, 1)[0].strip()
    s = re.split(r"\s+(?:for|is|writes|reports for)\s+", s, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    return re.sub(r"\s+", " ", s)


def _looks_like_person(s: Optional[str]) -> bool:
    if not s:
        return False
    s = _normalize_candidate(s)
    if len(s) < 4 or len(s) > 60:
        return False
    if s.lower() in KNOWN_PUBLISHER_PHRASES:
        return False
    words = s.split()
    if len(words) < 2 or len(words) > 5:
        return False
    if not all(w and w[0].isalpha() for w in words):
        return False
    lowered = [w.lower().strip(".,") for w in words]
    if any(t in PUBLISHER_TOKENS for t in lowered):
        return False
    if not any(w[0].isupper() for w in words):
        return False
    return True


def _clean(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = _normalize_candidate(s)
    words = s.split()
    return " ".join(
        w.title() if (w.isupper() and len(w) >= 3 and "." not in w) else w
        for w in words
    )


def _extract_from_byline(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    m = PERSON_NAME_RE.match(raw)
    if m and _looks_like_person(m.group("name")):
        return _clean(m.group("name"))
    if _looks_like_person(raw):
        return _clean(raw)
    return None


# ── Celery task ──────────────────────────────────────────────────────


@app.task(name="tasks.enrich_journalist_batch")
def enrich_journalist_batch(batch_size: int = 200) -> dict:
    """Pick up articles missing author_name + extract journalist name.

    Fast path only — Stage 1 (byline regex). Stage 2 (HTML re-fetch) is
    NOT run here because we want this task to be lightweight (<5s).
    HTML-only extractions are handled by the standalone backfill script
    or a separate slow-path task.
    """
    return asyncio.run(_run(batch_size))


async def _run(batch_size: int) -> dict:
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT id::text AS aid, byline
              FROM articles
             WHERE substrate_status = 'ok'
               AND author_name IS NULL
               AND collected_at > NOW() - INTERVAL '30 days'
             ORDER BY collected_at DESC
             LIMIT :n
        """), {"n": batch_size})).mappings().all()

    if not rows:
        return {"processed": 0, "extracted": 0, "message": "no pending articles"}

    extracted = 0
    async with get_db() as db:
        for r in rows:
            name = _extract_from_byline(r["byline"])
            # Empty string '' is the "tried, no name" sentinel — prevents re-pickup
            value = name if name else ""
            await db.execute(text("""
                UPDATE articles SET author_name = :n WHERE id::text = :id
            """), {"n": value, "id": r["aid"]})
            if name:
                extracted += 1
        await db.commit()

    result = {
        "processed": len(rows),
        "extracted": extracted,
        "extraction_rate": round(extracted / len(rows) * 100, 1),
    }
    logger.info("enrich_journalist_batch: %s", result)
    return result
