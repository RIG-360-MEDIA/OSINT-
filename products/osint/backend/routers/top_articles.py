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

import re
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


# ── diversity / de-duplication ───────────────────────────────────────────────
# The ranked pool is principal-weighted, so the top can fill with several copies
# of ONE event (same headline across outlets) or many stories about the same
# entity. Collapse near-identical headlines and cap any single matched entity so
# the cards stay varied — fresh region/topic stories take the freed slots.
_WORD = re.compile(r"[a-z0-9ఀ-౿]+")  # latin digits + Telugu block
_STOP = frozenset({"the", "a", "an", "to", "of", "in", "on", "for", "and", "at",
                   "by", "as", "with", "is", "be", "from", "into", "over"})


def _title_sig(title: str | None) -> str:
    """Order-independent signature of a headline (collapses near-duplicates)."""
    t = (title or "").lower()
    t = re.sub(r"\b\d{5,}\b", " ", t)       # strip long id numbers (…1529812)
    t = re.sub(r"\.html?\b", " ", t)         # strip trailing .html
    toks = [w for w in _WORD.findall(t) if len(w) > 2 and w not in _STOP]
    return " ".join(sorted(set(toks))[:8]) or t


def _name_bigrams(title: str | None, exclude: frozenset[str]) -> set[str]:
    """Consecutive name-like token pairs in a title (e.g. 'ramalinga reddy').

    Pairs containing an excluded token (the persona's principal) are dropped, so
    the principal may appear in several cards while a repeated OTHER person (the
    same off-state resignation written 3 ways) collapses to one."""
    toks = [w for w in _WORD.findall((title or "").lower())
            if len(w) >= 4 and w not in _STOP]
    out: set[str] = set()
    for a, b in zip(toks, toks[1:]):
        if a in exclude or b in exclude:
            continue
        out.add(f"{a} {b}")
    return out


def _diversify(ranked: list[dict[str, Any]], limit: int,
               primary_tok: str = "", principal_toks: frozenset[str] = frozenset(),
               ) -> list[dict[str, Any]]:
    """Pick `limit` distinct, varied, primary-state-first stories.

    - De-dup: same headline (signature) OR a repeated NON-principal person.
    - Variety: cap any one matched entity to ~half the row.
    - Andhra-first: stories about the primary state / the principal are taken
      before off-state stories, which only backfill leftover slots.
    """
    cap_ent = max(2, (limit + 1) // 2)
    seen_sig: set[str] = set()
    seen_person: set[str] = set()
    ent_count: dict[str, int] = {}
    chosen: list[dict[str, Any]] = []

    def _take(pool: list[dict[str, Any]]) -> None:
        for r in pool:
            if len(chosen) >= limit:
                return
            title = r.get("title")
            sig = _title_sig(title)
            if sig in seen_sig:
                continue                                  # same headline
            persons = _name_bigrams(title, principal_toks)
            if persons & seen_person:
                continue                                  # repeated other-person
            ent = (r.get("matched") or "").strip().lower()
            if ent and ent_count.get(ent, 0) >= cap_ent:
                continue                                  # one entity overused
            seen_sig.add(sig)
            seen_person.update(persons)
            if ent:
                ent_count[ent] = ent_count.get(ent, 0) + 1
            chosen.append(r)

    def _is_primary(r: dict[str, Any]) -> bool:
        text = f"{r.get('geo') or ''} {r.get('title') or ''}".lower()
        if primary_tok and primary_tok in text:
            return True
        return any(t in text for t in principal_toks)

    _take([r for r in ranked if _is_primary(r)])           # primary state / principal
    if len(chosen) < limit:
        _take([r for r in ranked if not _is_primary(r)])   # off-state backfill
    return chosen[:limit]


@router.get("/top-articles")
async def get_top_articles(
    limit: int = Query(default=8, ge=1, le=20),
    window_hours: int = Query(default=72, ge=6, le=2160),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    """Top-N relevance-ranked articles for the authenticated persona."""
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"]) if user else None
        if not prefs:
            return {"personalized": False, "articles": []}

        # Over-fetch a wider pool, then DIVERSIFY (de-dup same-event headlines +
        # cap any single entity) so the row isn't one principal story repeated.
        # A faster half-life (20h) keeps the set rotating with fresh news.
        ranked = await score_relevant(db, prefs, window_hours=window_hours,
                                      limit=max(limit * 6, 60), half_life_h=20.0)
        # Primary-state token (e.g. "andhra") + principal name tokens drive the
        # Andhra-first ordering and the principal-protected de-duplication.
        _states = (prefs.get("regions") or {}).get("states") or []
        primary_tok = next((w for w in re.findall(r"[a-z]+", (_states[0] if _states else "").lower())
                            if len(w) >= 4 and w not in _STOP), "")
        _pname = ((prefs.get("primary_subject_meta") or {}).get("name") or "").lower()
        principal_toks = frozenset(w for w in re.findall(r"[a-z]+", _pname) if len(w) >= 6)
        top = _diversify(ranked, limit, primary_tok=primary_tok, principal_toks=principal_toks)
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
        # Summaries must render in English too. The stored "translated" lead text
        # is still Telugu for ~84% of te articles, so translate the chosen summary
        # (cached in analytics.text_en) and surface the English as the card text.
        await i18n.attach_en(db, articles, "summary")
        for a in articles:
            if a.get("summary_en"):
                a["summary"] = a["summary_en"]
        return {"personalized": True, "articles": articles, "window_hours": window_hours}
