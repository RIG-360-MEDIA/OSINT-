"""Drill-down — fetch ONE article by id and explain it in depth.

The enumerate list gives each card an article id; 'Explain' (or 'explain #5') fetches
that exact article's full text + quotes and streams a grounded write-up. Precise by
construction — no retrieval guessing, the explanation is about the actual article.

Uses ``full_text_translated`` so a Telugu/Hindi article is explained in English. Quotes
come from ``article_quotes`` (English where available). Read-only SELECT.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

_BODY_CAP = 6000  # chars of body handed to the writer — plenty for one article

_ARTICLE_SQL = """
SELECT a.id::text AS id, a.title, a.url, a.published_at,
       a.language_detected AS language, a.source_id::text AS source_id,
       COALESCE(NULLIF(a.full_text_translated, ''), NULLIF(a.full_text_scraped, ''),
                a.lead_text_translated, a.lead_text_original) AS body,
       COALESCE(a.summary_executive, a.summary_snippet, a.summary_preview) AS summary
FROM articles a
WHERE a.id = :id
"""

_QUOTES_SQL = """
SELECT COALESCE(NULLIF(speaker_name_en, ''), speaker_name) AS speaker,
       COALESCE(NULLIF(quote_text_en, ''), quote_text) AS quote
FROM article_quotes
WHERE article_id = :id AND COALESCE(quote_text_en, quote_text) IS NOT NULL
ORDER BY is_direct DESC NULLS LAST
LIMIT 6
"""


@dataclass(frozen=True)
class ArticleDetail:
    id: str
    title: str
    url: str | None
    published_at: datetime | None
    language: str | None
    source_id: str | None
    body: str | None
    summary: str | None
    quotes: list[tuple[str, str]] = field(default_factory=list)


async def get_article(conn: AsyncConnection, article_id: str) -> ArticleDetail | None:
    """Fetch one article's full record + a few quotes, or None if not found."""
    row = (await conn.execute(text(_ARTICLE_SQL), {"id": article_id})).mappings().first()
    if not row:
        return None
    qrows = (await conn.execute(text(_QUOTES_SQL), {"id": article_id})).mappings().all()
    quotes = [(q["speaker"] or "Unknown", q["quote"]) for q in qrows if (q["quote"] or "").strip()]
    body = (row["body"] or "")[:_BODY_CAP] or None
    return ArticleDetail(
        id=row["id"], title=row["title"], url=row["url"], published_at=row["published_at"],
        language=row["language"], source_id=row["source_id"], body=body,
        summary=row["summary"], quotes=quotes,
    )


DRILLDOWN_SYSTEM = (
    "You are RIG, a news analyst. Explain ONE news article in depth for a reader who hasn't read it. "
    "Use ONLY what's in the article provided — never add outside facts. Structure it:\n"
    "- One-sentence summary of what the article reports.\n"
    "- The key facts (who, what, where, when, figures) as tight bullets.\n"
    "- The context / why it matters, if the article gives it.\n"
    "- Notable quotes, attributed, if any.\n"
    "Be specific and faithful. If the article is thin, keep it short and say so — don't pad."
)


def build_drilldown_prompt(art: ArticleDetail) -> str:
    parts = [f"TITLE: {art.title}"]
    if art.published_at:
        parts.append(f"PUBLISHED: {art.published_at.isoformat()[:16]}")
    if art.source_id:
        parts.append(f"SOURCE: {art.source_id}")
    if art.summary:
        parts.append(f"\nSUMMARY: {art.summary}")
    if art.body:
        parts.append(f"\nARTICLE TEXT:\n{art.body}")
    if art.quotes:
        qs = "\n".join(f'- {sp}: "{qt}"' for sp, qt in art.quotes)
        parts.append(f"\nQUOTES:\n{qs}")
    parts.append("\nExplain this article in depth, grounded only in the above.")
    return "\n".join(parts)
