"""GET /api/brief/voices — Voices Overnight panel.

Phase 4.2 of the brief redesign. Three sub-sections:

  featured       The single best quote of the sim-since window — length-prioritised,
                 with speaker + source + timestamp + a per-article-stance tag.
  media_voices   Editorial-style quotes (speaker_entity_id IS NULL — anonymous /
                 outlet attribution) with outlet + language + stance.
  opp_voices     Politician quotes — speaker_entity_id IS NOT NULL (matched to
                 entity_dictionary). Each carries speaker + party (when known) +
                 stance + role hint.

Same filter convention as Phase 4.1:
  ?since_hours=12   width of the window
  ?country=IN       restrict articles by source_country
  ?limit=5          per-section limit
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import text

from db import get_db

router = APIRouter(prefix="/api/brief", tags=["brief"])


def _stance_tag(intensity: float | None) -> str:
    if intensity is None: return "neutral"
    if intensity >= 0.15:  return "supportive"
    if intensity <= -0.15: return "critical"
    return "neutral"


def _fmt_ts(dt: Any) -> str:
    return dt.strftime("%d %b · %H:%M IST") if dt else "—"


@router.get("/voices")
async def get_voices(
    since_hours: int = Query(default=12, ge=1, le=168),
    country: str | None = Query(default=None, pattern=r"^[A-Z]{2}$"),
    limit: int = Query(default=5, ge=1, le=20),
) -> dict[str, Any]:
    """Voices Overnight: featured quote + editorial voices + opposition voices."""
    cc = "AND a.source_country = :country" if country else ""
    params: dict[str, Any] = {"limit": int(limit), "hours": int(since_hours)}
    if country:
        params["country"] = country

    async with get_db() as db:
        # ─── Featured: best-length quote in window ──────────────────────────
        feat_row = (await db.execute(text(f"""
            SELECT aq.quote_text, aq.speaker_name, aq.context,
                   COALESCE(aq.quote_text_en, aq.quote_text) AS quote_en,
                   s.name AS outlet, a.collected_at, a.language_iso,
                   (SELECT AVG(st.intensity) FROM article_stances st
                     WHERE st.article_id = a.id) AS intensity
              FROM article_quotes aq
              JOIN articles a ON a.id = aq.article_id
              JOIN sources s  ON s.id = a.source_id
             WHERE LENGTH(aq.quote_text) BETWEEN 60 AND 280
               AND aq.is_direct = TRUE
               AND a.collected_at >= analytics.now_sim() - (CAST(:hours AS TEXT) || ' hours')::INTERVAL
               AND a.collected_at <= analytics.now_sim()
               {cc}
             ORDER BY LENGTH(aq.quote_text) DESC, a.collected_at DESC
             LIMIT 1
        """), params)).fetchone()

        featured = None
        if feat_row:
            featured = {
                "text": feat_row.quote_text[:280],
                "text_en": feat_row.quote_en[:280] if feat_row.quote_en else None,
                "speaker": feat_row.speaker_name or "—",
                "source": feat_row.outlet or "—",
                "lang": feat_row.language_iso or "en",
                "timestamp": _fmt_ts(feat_row.collected_at),
                "stance": _stance_tag(feat_row.intensity),
                "context": (feat_row.context[:180] if feat_row.context else None),
            }

        # ─── Media voices: editorial / anonymous-speaker quotes ─────────────
        media_rows = (await db.execute(text(f"""
            SELECT aq.quote_text, aq.speaker_name,
                   s.name AS outlet, a.collected_at, a.language_iso,
                   (SELECT AVG(st.intensity) FROM article_stances st
                     WHERE st.article_id = a.id) AS intensity
              FROM article_quotes aq
              JOIN articles a ON a.id = aq.article_id
              JOIN sources s  ON s.id = a.source_id
             WHERE aq.speaker_entity_id IS NULL
               AND LENGTH(aq.quote_text) BETWEEN 40 AND 280
               AND aq.is_direct = TRUE
               AND a.collected_at >= analytics.now_sim() - (CAST(:hours AS TEXT) || ' hours')::INTERVAL
               AND a.collected_at <= analytics.now_sim()
               {cc}
             ORDER BY a.collected_at DESC
             LIMIT :limit
        """), params)).fetchall()
        media_voices = [{
            "outlet": r.outlet or "—",
            "lang": r.language_iso or "en",
            "speaker": r.speaker_name or "—",
            "text": r.quote_text[:180],
            "stance": _stance_tag(r.intensity),
            "timestamp": _fmt_ts(r.collected_at),
        } for r in media_rows]

        # ─── Opposition voices: politician quotes (entity-matched) ──────────
        opp_rows = (await db.execute(text(f"""
            SELECT aq.quote_text, aq.speaker_name, aq.speaker_entity_id::text AS eid,
                   ed.canonical_name, ed.entity_type,
                   s.name AS outlet, a.collected_at, a.language_iso,
                   (SELECT AVG(st.intensity) FROM article_stances st
                     WHERE st.article_id = a.id) AS intensity
              FROM article_quotes aq
              JOIN articles a ON a.id = aq.article_id
              JOIN sources s  ON s.id = a.source_id
              LEFT JOIN entity_dictionary ed ON ed.id = aq.speaker_entity_id
             WHERE aq.speaker_entity_id IS NOT NULL
               AND LENGTH(aq.quote_text) BETWEEN 40 AND 280
               AND aq.is_direct = TRUE
               AND a.collected_at >= analytics.now_sim() - (CAST(:hours AS TEXT) || ' hours')::INTERVAL
               AND a.collected_at <= analytics.now_sim()
               {cc}
             ORDER BY a.collected_at DESC
             LIMIT :limit
        """), params)).fetchall()
        opp_voices = [{
            "speaker": r.canonical_name or r.speaker_name or "—",
            "role": (r.entity_type or "").replace("_", " ").title() or "—",
            "entity_id": r.eid,
            "text": r.quote_text[:180],
            "outlet": r.outlet or "—",
            "lang": r.language_iso or "en",
            "stance": _stance_tag(r.intensity),
            "timestamp": _fmt_ts(r.collected_at),
        } for r in opp_rows]

    return {
        "featured": featured,
        "media_voices": media_voices,
        "opp_voices": opp_voices,
        "filters": {"since_hours": since_hours, "country": country, "limit": limit},
    }
