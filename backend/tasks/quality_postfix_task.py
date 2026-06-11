"""quality_postfix_task.py — Periodic post-extraction cleanup.

Runs every 15 minutes on articles ingested in the last hour. Applies the
same fixes we did one-shot for T1/T2 against the legacy corpus, but
incrementally on new arrivals. This way new articles auto-clean without
needing substrate prompt edits.

Two passes per run:
  - T11: Unicode-script language override on title (en-tagged with
    Indic-script titles get re-tagged correctly).
  - T12: is_future = (effective_event_date > published_at::date). Stops
    new is_future-vs-past-date contradictions from accumulating.

Idempotent. Safe to call repeatedly. Logs counts updated.
"""
from __future__ import annotations

import asyncio
import logging
import re

from celery import shared_task
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Unicode script → ISO-639-1 code (same map as T2_fix_language_mistags.py)
SCRIPT_TO_LANG: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[ఀ-౿]"), "te"),
    (re.compile(r"[ঀ-৿]"), "bn"),
    (re.compile(r"[஀-௿]"), "ta"),
    (re.compile(r"[ಀ-೿]"), "kn"),
    (re.compile(r"[ഀ-ൿ]"), "ml"),
    (re.compile(r"[઀-૿]"), "gu"),
    (re.compile(r"[਀-੿]"), "pa"),
    (re.compile(r"[ऀ-ॿ]"), "hi"),
    (re.compile(r"[؀-ۿ]"), "ur"),
]


def _detect_from_script(title: str) -> str | None:
    if not title:
        return None
    matches: list[tuple[str, int]] = []
    for pat, code in SCRIPT_TO_LANG:
        hits = len(pat.findall(title))
        if hits >= 3:
            matches.append((code, hits))
    if not matches:
        return None
    matches.sort(key=lambda x: x[1], reverse=True)
    return matches[0][0]


async def _postfix_language(db, lookback_hours: int) -> int:
    """Override language_detected when title's script disagrees with it."""
    rows = (await db.execute(text("""
        SELECT id::text AS aid, language_detected, title
          FROM articles
         WHERE collected_at >= NOW() - make_interval(hours => :h)
           AND title IS NOT NULL
           AND (
             (language_detected='en' AND title ~ '[ఀ-౿ऀ-ॿঀ-৿஀-௿ಀ-೿ഀ-ൿ઀-૿਀-੿]')
             OR (language_detected='te' AND title !~ '[ఀ-౿]' AND LENGTH(title) > 5)
           )
    """), {"h": int(lookback_hours)})).fetchall()

    updated = 0
    for r in rows:
        new_lang = _detect_from_script(r.title)
        if new_lang and new_lang != r.language_detected:
            await db.execute(text(
                "UPDATE articles SET language_detected = :l "
                "WHERE id = CAST(:a AS uuid)"
            ), {"a": r.aid, "l": new_lang})
            updated += 1
    return updated


async def _postfix_is_future(db, lookback_hours: int) -> int:
    """Set is_future = (effective_event_date > published_at::date) for new events."""
    # Single bulk UPDATE — much faster than per-row loop
    result = await db.execute(text("""
        UPDATE article_events ae
           SET is_future = (ae.effective_event_date > a.published_at::date)
          FROM articles a
         WHERE ae.article_id = a.id
           AND a.collected_at >= NOW() - make_interval(hours => :h)
           AND ae.effective_event_date IS NOT NULL
           AND a.published_at IS NOT NULL
           AND ae.is_future IS DISTINCT FROM
               (ae.effective_event_date > a.published_at::date)
    """), {"h": int(lookback_hours)})
    return result.rowcount or 0


async def _run(lookback_hours: int = 1) -> dict[str, int]:
    from backend.database import get_db
    async with get_db() as db:
        n_lang = await _postfix_language(db, lookback_hours)
        n_isf = await _postfix_is_future(db, lookback_hours)
        await db.commit()
    return {"language_fixed": n_lang, "is_future_fixed": n_isf}


@shared_task(
    name="tasks.quality.postfix",
    bind=True,
    queue="nlp",
    soft_time_limit=120,
    time_limit=180,
)
def quality_postfix_task(self, lookback_hours: int = 1) -> dict[str, int]:
    """Periodic cleanup — runs every 15 min via Celery beat.

    Default lookback: 1 hour (overlaps subsequent runs by 45 min for safety).
    """
    try:
        result = asyncio.run(_run(int(lookback_hours)))
        logger.info("quality_postfix: %s", result)
        return result
    except Exception as exc:
        logger.exception("quality_postfix failed: %s", exc)
        return {"error": str(exc)[:200]}
