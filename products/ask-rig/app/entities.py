"""Feature 3 — canonical entity feed (cross-language).

Two steps, deliberately separated so we never silently merge entities:
  1. RESOLVE a search term to canonical entities (``entity_lookup`` exact +
     ``entity_dictionary`` fuzzy), returning MULTIPLE ranked candidates — the
     disambiguation guard (Lalit Modi vs Narendra Modi are distinct rows).
  2. FEED an entity's recent articles across languages via the 1.33M-row
     ``article_entity_mentions`` matview joined to ``articles``.
Read-only SELECT throughout.
"""
from __future__ import annotations

import re
from typing import Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.schemas import EntityCandidate, RetrievedDoc


def normalize_entity(query: str) -> str:
    """Lowercase + collapse whitespace — matches ``entity_lookup.name_norm``."""
    return re.sub(r"\s+", " ", query.strip().lower())


# Leading/trailing chatter we strip so a SENTENCE still resolves to a name.
_FILLER = frozenset({
    "tell", "show", "give", "get", "find", "search", "for", "look", "up", "me", "i",
    "want", "need", "what", "whats", "what's", "who", "whos", "who's", "is", "are",
    "was", "the", "a", "an", "latest", "top", "recent", "news", "update", "updates",
    "story", "stories", "coverage", "about", "on", "of", "to", "please", "all", "any",
    "some", "more", "today", "now", "headlines",
})


def clean_entity_query(query: str) -> str:
    """Extract the likely entity NAME from a natural-language query by trimming
    leading/trailing filler words. "tell me top news about revanth reddy" → "revanth reddy".
    Falls back to the normalized query if nothing's left."""
    norm = normalize_entity(query)
    toks = norm.split()
    i, j = 0, len(toks)
    while i < j and toks[i] in _FILLER:
        i += 1
    while j > i and toks[j - 1] in _FILLER:
        j -= 1
    return " ".join(toks[i:j]) or norm


def is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


# Three ways to match, so a NAME, an ALIAS, or a SENTENCE all resolve:
#  1) exact normalized lookup (covers aliases)
#  2) fuzzy: a canonical name CONTAINS the cleaned query
#  3) reverse: a canonical name APPEARS INSIDE the raw query (sentence handling)
# Only canonical rows (redirected_to IS NULL); rank by coverage so the most-covered
# entity mentioned wins disambiguation.
_SEARCH_SQL = """
WITH matches AS (
  SELECT entity_id FROM entity_lookup WHERE name_norm = :norm
  UNION
  SELECT id FROM entity_dictionary WHERE canonical_name ILIKE :like
  UNION
  SELECT id FROM entity_dictionary
    WHERE char_length(canonical_name) >= 4
      AND :orig LIKE '%' || lower(canonical_name) || '%'
)
SELECT d.id::text AS entity_id, d.canonical_name, d.entity_type, d.party, d.state,
       (SELECT count(*) FROM article_entity_mentions m WHERE m.entity_id = d.id) AS n_articles
FROM entity_dictionary d
WHERE d.id IN (SELECT entity_id FROM matches) AND d.redirected_to IS NULL
ORDER BY n_articles DESC, d.canonical_name
LIMIT :limit
"""

_FEED_SQL = """
SELECT a.id::text AS id, a.title, a.lead_text_translated AS snippet, a.url,
       a.published_at, a.source_id::text AS source_id, a.language_detected AS language
FROM article_entity_mentions m
JOIN articles a ON a.id = m.article_id
WHERE m.entity_id = :eid AND a.substrate_status = 'ok' AND NOT a.is_duplicate{lang}
ORDER BY a.published_at DESC NULLS LAST
LIMIT :k
"""


async def search_entities(
    conn: AsyncConnection, query: str, limit: int = 10
) -> list[EntityCandidate]:
    orig = normalize_entity(query)
    cleaned = clean_entity_query(query)
    # Escape LIKE wildcards in user input so "50%" doesn't become a wildcard.
    like = "%" + re.sub(r"([%_\\])", r"\\\1", cleaned) + "%"
    rows = (
        await conn.execute(
            text(_SEARCH_SQL), {"norm": cleaned, "like": like, "orig": orig, "limit": limit}
        )
    ).mappings().all()
    return [
        EntityCandidate(
            entity_id=r["entity_id"],
            canonical_name=r["canonical_name"],
            entity_type=r["entity_type"],
            party=r["party"],
            state=r["state"],
            n_articles=int(r["n_articles"] or 0),
        )
        for r in rows
    ]


async def entity_feed(
    conn: AsyncConnection,
    settings: Settings,
    entity_id: str,
    k: int = 20,
    languages: Sequence[str] | None = None,
) -> list[RetrievedDoc]:
    lang = " AND a.language_detected = ANY(:langs)" if languages else ""
    params: dict = {"eid": entity_id, "k": k}
    if languages:
        params["langs"] = list(languages)
    rows = (await conn.execute(text(_FEED_SQL.format(lang=lang)), params)).mappings().all()
    return [
        RetrievedDoc(
            id=r["id"],
            title=r["title"],
            snippet=(r["snippet"] or "")[:300] or None,
            url=r["url"],
            published_at=r["published_at"],
            source_id=r["source_id"],
            language=r["language"],
            score=0.0,  # feed is recency-ordered, not scored
            vec_rank=None,
            lex_rank=None,
        )
        for r in rows
    ]
