"""Audit-queue helpers for the /observe page.

Reads:
  * audit_queue() — articles that LLM-judge flagged or that auto-checks flagged
  * audit_decision() — write a 'correct' | 'wrong' | 'unsure' row

Owned by: backend/observability/audit_queue.py.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text


async def audit_queue(db, limit: int = 30) -> dict[str, Any]:
    """Articles that auto-checks flagged as likely-wrong.

    Heuristics (deliberately broad — surfaces obvious extraction misses):
      * article_claims.subject_text is the literal placeholder 'article'
      * is_future flag = TRUE but effective_event_date < published_at
      * lang mismatch (language_detected vs script in title)
    """
    rows = (await db.execute(text("""
        WITH flagged AS (
          -- Placeholder subject
          SELECT DISTINCT ac.article_id, 'placeholder_subject' AS flag, ac.subject_text AS hint
            FROM article_claims ac
           WHERE LOWER(ac.subject_text) IN ('article','story','report','piece','news')
          UNION
          -- is_future contradiction
          SELECT DISTINCT ae.article_id, 'is_future_contradicts_date' AS flag,
                 ae.effective_event_date::text AS hint
            FROM article_events ae
            JOIN articles a ON a.id = ae.article_id
           WHERE ae.is_future = TRUE
             AND ae.effective_event_date < a.published_at::date - INTERVAL '60 days'
          UNION
          -- Language mistag: en-tagged with Telugu script
          SELECT DISTINCT a.id AS article_id, 'lang_mistag_telugu' AS flag,
                 LEFT(a.title, 60) AS hint
            FROM articles a
           WHERE a.language_detected = 'en'
             AND a.title ~ '[ఀ-౿]'
        )
        SELECT f.article_id::text AS aid, f.flag, f.hint,
               s.name AS source, a.title, a.collected_at,
               (SELECT verdict FROM audit_decisions ad
                 WHERE ad.article_id = a.id
                   AND ad.field_name = f.flag
                   AND ad.extraction_version = a.extraction_version
                 LIMIT 1) AS existing_verdict
          FROM flagged f
          JOIN articles a ON a.id = f.article_id
          JOIN sources s ON s.id = a.source_id
         WHERE a.substrate_status = 'ok'
         ORDER BY a.collected_at DESC NULLS LAST
         LIMIT :lim
    """), {"lim": int(limit)})).fetchall()
    return {
        "queue": [
            {"aid": r.aid, "flag": r.flag, "hint": (r.hint or "")[:120],
             "source": r.source, "title": (r.title or "")[:160],
             "collected_at": r.collected_at.isoformat() if r.collected_at else None,
             "existing_verdict": r.existing_verdict}
            for r in rows
        ]
    }


async def record_decision(
    db,
    *,
    article_id: str,
    field_name: str,
    extraction_version: int,
    verdict: str,
    note: str | None,
    decided_by: str | None,
) -> dict[str, Any]:
    """Insert or update an audit decision. Returns the persisted row."""
    if verdict not in ("correct", "wrong", "unsure"):
        raise ValueError(f"Invalid verdict: {verdict}")
    row = (await db.execute(text("""
        INSERT INTO audit_decisions
            (article_id, field_name, extraction_version, verdict, note, decided_by)
        VALUES (CAST(:aid AS uuid), :field, :ver, :verdict, :note,
                CAST(:by AS uuid))
        ON CONFLICT (article_id, field_name, extraction_version) DO UPDATE
            SET verdict = EXCLUDED.verdict,
                note = EXCLUDED.note,
                decided_by = EXCLUDED.decided_by,
                decided_at = NOW()
        RETURNING id::text AS id, decided_at
    """), {
        "aid": article_id,
        "field": field_name,
        "ver": int(extraction_version),
        "verdict": verdict,
        "note": note,
        "by": decided_by,
    })).fetchone()
    return {"id": row.id, "decided_at": row.decided_at.isoformat()}
