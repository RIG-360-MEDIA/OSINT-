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

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from auth.middleware import get_optional_user
from brief_prefs import load_prefs
from db import get_db
from relevance import score_relevant

router = APIRouter(prefix="/api/brief", tags=["brief"])


def _stance_tag(intensity: float | None) -> str:
    if intensity is None: return "neutral"
    if intensity >= 0.15:  return "supportive"
    if intensity <= -0.15: return "critical"
    return "neutral"


def _fmt_ts(dt: Any) -> str:
    return dt.strftime("%d %b · %H:%M IST") if dt else "—"


async def _personal_voices(db, prefs: dict[str, Any], limit: int,
                           window_hours: int = 72) -> list[dict[str, Any]]:
    """Real, attributed quotes from the user's OWN relevant coverage.

    Pulls direct quotes from the user's relevance stream, watchlist speakers
    first, one quote per speaker for variety — so a Telangana CM hears Revanth
    / KTR / Harish Rao, a Delhi CM hears Rekha Gupta / Kejriwal / Atishi. Maps
    each speaker to the watchlist for role + party; English text preferred.
    """
    scored = await score_relevant(db, prefs, window_hours=window_hours, limit=160)
    if not scored:
        return []
    ids = [r["id"] for r in scored]
    meta = (prefs.get("watchlist") or {}).get("entity_meta") or []
    wl_ids = [m["id"] for m in meta if m.get("id")] or ["00000000-0000-0000-0000-000000000000"]
    wl_by_id = {m["id"]: m for m in meta if m.get("id")}
    wl_by_name = {(m.get("name") or "").lower(): m for m in meta if m.get("name")}

    rows = (await db.execute(text("""
        SELECT aq.quote_text, COALESCE(aq.quote_text_en, aq.quote_text) AS quote_en,
               aq.speaker_name, aq.speaker_entity_id::text AS eid,
               ed.canonical_name, ed.entity_type,
               s.name AS outlet, a.url, a.collected_at, a.language_iso,
               (SELECT AVG(st.intensity) FROM article_stances st WHERE st.article_id = a.id) AS intensity
          FROM article_quotes aq
          JOIN articles a ON a.id = aq.article_id
          JOIN sources s  ON s.id = a.source_id
          LEFT JOIN entity_dictionary ed ON ed.id = aq.speaker_entity_id
         WHERE aq.article_id = ANY(CAST(:ids AS uuid[]))
           AND aq.is_direct = TRUE
           AND LENGTH(aq.quote_text) BETWEEN 50 AND 280
         ORDER BY (CASE WHEN aq.speaker_entity_id = ANY(CAST(:wl AS uuid[])) THEN 0 ELSE 1 END),
                  LENGTH(aq.quote_text) DESC, a.collected_at DESC
         LIMIT 80
    """), {"ids": ids, "wl": wl_ids})).fetchall()

    voices: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in rows:
        name = r.canonical_name or r.speaker_name
        if not name or len(name) < 3:
            continue
        key = name.lower()
        if key in seen:
            continue
        m = wl_by_id.get(r.eid) or wl_by_name.get(key)
        role = (m.get("role") if m else None) or (
            (r.entity_type or "").replace("_", " ").title() if r.entity_type else None)
        party = m.get("party") if m else None
        role_line = " · ".join([x for x in [role, party] if x]) or "Voice"
        stance = _stance_tag(float(r.intensity) if r.intensity is not None else None)
        camp = (m or {}).get("camp")
        # Pill = political alignment (reliable, from the watchlist). The per-article
        # stance is an unreliable proxy for a quote's actual stance, so we do NOT
        # surface it as a supportive/critical claim; we only use camp to tint the
        # card border (opposition reads rose, govt green).
        border = {"opposition": "critical", "rival": "critical",
                  "govt": "supportive"}.get(camp or "", "neutral")
        seen.add(key)
        voices.append({
            "speaker": name,
            "role": role_line,
            "party": party,
            "camp": camp,
            "stance": border,
            "contextTag": camp.upper() if camp else None,
            "quote": (r.quote_en or r.quote_text)[:280],
            "source": r.outlet or "—",
            "url": r.url,
            "lang": r.language_iso or "en",
            "init": "".join(w[0] for w in name.split()[:2]).upper(),
            "timestamp": _fmt_ts(r.collected_at),
            "watchlist": bool(m),
        })
        if len(voices) >= limit:
            break
    return voices


@router.get("/voices")
async def get_voices(
    since_hours: int = Query(default=12, ge=1, le=168),
    country: str | None = Query(default=None, pattern=r"^[A-Z]{2}$"),
    limit: int = Query(default=5, ge=1, le=20),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    """Voices Overnight. Personalised: real quotes from the signed-in user's
    own relevant coverage (watchlist speakers first). Anonymous / no-prefs
    requests get the global featured + editorial + opposition voices."""
    cc = "AND a.source_country = :country" if country else ""
    # since_hours bounded 1-168 by Pydantic, safe to interpolate as literal.
    window = f"INTERVAL '{int(since_hours)} hours'"
    params: dict[str, Any] = {"limit": int(limit)}
    if country:
        params["country"] = country

    async with get_db() as db:
        # ─── Personalised path: quotes from the user's own relevant coverage ─
        prefs = await load_prefs(db, user["id"]) if user else None
        if prefs:
            voices = await _personal_voices(db, prefs, int(limit))
            if voices:
                return {"voices": voices, "personalized": True, "featured": None,
                        "media_voices": [], "opp_voices": [],
                        "filters": {"since_hours": since_hours, "country": country, "limit": limit}}

        # ─── Featured: best-length quote in window (global fallback) ─────────
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
               AND a.collected_at >= analytics.now_sim() - {window}
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
               AND a.collected_at >= analytics.now_sim() - {window}
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
               -- Phase-4 fix: filter to actual people. 'location' (Litani River)
               -- and 'role' (generic titles) were getting through as 'opp voices'.
               AND LOWER(ed.entity_type) IN ('person', 'politician')
               AND LENGTH(aq.quote_text) BETWEEN 40 AND 280
               AND aq.is_direct = TRUE
               AND a.collected_at >= analytics.now_sim() - {window}
               AND a.collected_at <= analytics.now_sim()
               {cc}
             ORDER BY a.collected_at DESC
             LIMIT :limit
        """), params)).fetchall()
        opp_voices = [{
            "speaker": r.canonical_name or r.speaker_name or "—",
            "role": (r.entity_type or "person").replace("_", " ").title() or "Person",
            "entity_id": r.eid,
            "text": r.quote_text[:180],
            "outlet": r.outlet or "—",
            "lang": r.language_iso or "en",
            "stance": _stance_tag(r.intensity),
            "timestamp": _fmt_ts(r.collected_at),
        } for r in opp_rows]

    return {
        "voices": [],
        "personalized": False,
        "featured": featured,
        "media_voices": media_voices,
        "opp_voices": opp_voices,
        "filters": {"since_hours": since_hours, "country": country, "limit": limit},
    }
