"""GET /api/brief/top-articles — the persona's most relevant ARTICLES.

Powers Home's "Top Articles For You" cards. Ranks INDIVIDUAL articles (not
clusters) via the relevance core (`score_relevant`), then enriches the top N
with age + tone + thumbnail for the cards.

Tier-aware by construction: `score_relevant` reads the watchlist `tier` —
national/`extended` entities (Modi, neighbour CMs) surface ONLY when a story
also touches the persona's region/subject, so standalone national noise is
suppressed (proven live for the AP persona). Fully generic per persona.

The per-card "for you" strategic line is a separate LLM surface
(`textual.story_for_you`) layered on in a follow-up — this endpoint returns the
ranked, enriched cards without it so the section ships first.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from auth.middleware import get_optional_user
from brief_prefs import load_prefs
from db import get_db
from relevance import score_relevant
import i18n

router = APIRouter(prefix="/api/brief", tags=["brief"])


def _tone(intensities: list[float]) -> str:
    """Aggregate article stance polarity → display tone (matches the card UI)."""
    if not intensities:
        return "neutral"
    avg = sum(intensities) / len(intensities)
    if avg >= 0.10:
        return "supportive"
    if avg <= -0.10:
        return "hostile"
    return "neutral"


def _age(age_hours: float | None) -> str:
    if age_hours is None:
        return "—"
    if age_hours < 1:
        return "now"
    if age_hours < 24:
        return f"{int(age_hours)}h"
    return f"{int(age_hours // 24)}d"


@router.get("/top-articles")
async def get_top_articles(
    limit: int = Query(default=8, ge=1, le=20),
    window_hours: int = Query(default=168, ge=6, le=2160),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    """Top-N relevance-ranked articles for the authenticated persona."""
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"]) if user else None
        if not prefs:
            return {"personalized": False, "articles": []}

        # Over-fetch then trim — score_relevant already applies the tier-aware,
        # freshness-decayed, salience-first ranking.
        ranked = await score_relevant(db, prefs, window_hours=window_hours, limit=max(limit * 4, 40))
        top = ranked[:limit]
        if not top:
            return {"personalized": True, "articles": [], "window_hours": window_hours}

        ids = [r["id"] for r in top]
        meta = {r.id: r for r in (await db.execute(text("""
            SELECT a.id::text AS id, a.thumbnail_url, a.url, a.language_iso,
                   EXTRACT(EPOCH FROM (analytics.now_sim() - a.collected_at)) / 3600.0 AS age_h
              FROM articles a WHERE a.id = ANY(CAST(:ids AS uuid[]))
        """), {"ids": ids})).fetchall()}

        stances: dict[str, list[float]] = {}
        for row in (await db.execute(text("""
            SELECT article_id::text AS id, intensity FROM article_stances
             WHERE article_id = ANY(CAST(:ids AS uuid[])) AND intensity IS NOT NULL
        """), {"ids": ids})).fetchall():
            stances.setdefault(row.id, []).append(float(row.intensity))

        articles = []
        for i, r in enumerate(top):
            m = meta.get(r["id"])
            articles.append({
                "rank": i + 1,
                "id": r["id"],
                "headline": r["title"],
                "summary": r.get("summary"),
                "source": r["source"],
                "age": _age(float(m.age_h) if m and m.age_h is not None else None),
                "tone": _tone(stances.get(r["id"], [])),
                "matched": r.get("matched"),
                "topic": r.get("topic"),
                "geo": r.get("geo"),
                "score": r["score"],
                "lang": (m.language_iso if m else None),
                "url": (m.url if m else None),
                "thumbnail": (m.thumbnail_url if m else None),
            })
        await i18n.attach_en(db, articles, "headline")
        return {"personalized": True, "articles": articles, "window_hours": window_hours}
