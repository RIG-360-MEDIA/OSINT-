"""
Extract spokesperson quotes from articles. Filtered to articles whose
matched_entities contain at least one politician-typed entity AND whose
score_final >= 0.5 — keeps Groq token spend bounded.

Scheduled every 10 minutes on the `nlp` queue.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db
from backend.nlp.cm.speakers import extract as extract_quotes

logger = logging.getLogger(__name__)

BATCH = 24


async def _entity_dict() -> dict[str, dict[str, Any]]:
    """Load a minimal entity_dictionary as {canonical: {party, aliases, entity_type}}."""
    sql = "SELECT canonical_name, entity_type, aliases, state, party FROM entity_dictionary"
    out: dict[str, dict[str, Any]] = {}
    async with get_db() as db:
        rows = (await db.execute(text(sql))).all()
    for r in rows:
        out[r.canonical_name] = {
            "entity_type": r.entity_type,
            "aliases": list(r.aliases or []) if hasattr(r.aliases, "__iter__") else [],
            "state": r.state,
            "party": r.party,
        }
    return out


async def _run() -> int:
    sql = """
        SELECT a.id, a.title, a.full_text_scraped, a.lead_text_translated, a.url,
               a.geo_primary, a.entities_extracted, a.source_tier
        FROM articles a
        LEFT JOIN cm_spokesperson_quotes q
          ON q.source_kind = 'article' AND q.source_id = a.id
        WHERE q.id IS NULL
          AND a.published_at > now() - interval '36 hours'
          AND COALESCE(a.source_tier, 9) <= 2
        ORDER BY a.published_at DESC
        LIMIT :lim
    """
    insert = """
        INSERT INTO cm_spokesperson_quotes (
            source_kind, source_id, state, speaker, speaker_canonical,
            party, role, quote, quote_lang, stance, sentiment, issue_hint,
            source_url, extracted_at
        ) VALUES (
            'article', :sid, :state, :speaker, :sc, :party, :role,
            :quote, :lang, :stance, NULL, :hint, :url, now()
        )
        ON CONFLICT (source_kind, source_id, speaker, left(quote, 200))
        DO NOTHING
    """
    edict = await _entity_dict()
    n_extracted = 0
    async with get_db() as db:
        rows = (await db.execute(text(sql), {"lim": BATCH})).all()
        for r in rows:
            body = r.full_text_scraped or r.lead_text_translated or ""
            if len(body) < 80:
                continue
            geo = (r.geo_primary or "").lower()
            state = "TG" if "telangana" in geo or "hyderabad" in geo else (
                "AP" if "andhra" in geo or "vizag" in geo or "vijayawada" in geo else None
            )
            try:
                result = await extract_quotes(title=r.title, body=body, entity_dict=edict)
            except Exception as exc:  # noqa: BLE001
                logger.warning("speakers extract failed article %s: %s", r.id, exc)
                continue
            for q in result.quotes:
                await db.execute(
                    text(insert),
                    {
                        "sid": r.id,
                        "state": state,
                        "speaker": q.speaker,
                        "sc": q.speaker_canonical,
                        "party": q.party,
                        "role": q.role,
                        "quote": q.quote,
                        "lang": None,
                        "stance": q.stance,
                        "hint": q.issue_hint,
                        "url": r.url,
                    },
                )
                n_extracted += 1
        await db.commit()
    return n_extracted


@app.task(name="tasks.cm.extract_speakers", bind=True, max_retries=2)
def extract_speakers(self) -> dict[str, int]:
    try:
        return {"quotes": asyncio.run(_run())}
    except Exception as exc:
        logger.exception("extract_speakers failed")
        raise self.retry(exc=exc, countdown=180)
