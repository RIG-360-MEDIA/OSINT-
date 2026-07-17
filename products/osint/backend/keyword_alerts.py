"""Keyword alert evaluation — velocity + sentiment-flip + harmful-actor detection.

Reads active analytics.keyword_watch rows, compares the current window against the
prior window (a rolling baseline), and writes analytics.keyword_alerts when a
signal crosses threshold. Called by a Celery beat job (Phase 5) and directly by
the /track flow for an immediate first evaluation.

Directed + honest: only fires on real deltas; deduplicates by not re-firing the
same alert type within a cooldown window.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

SPIKE_PCT = 50.0          # +50% volume vs prior window => spike
SENTIMENT_FLIP = 0.30     # lean swing >= 0.30 => sentiment flip
COOLDOWN_HOURS = 12       # don't re-fire the same alert type within this window


def _word_pattern(q: str) -> str:
    import re
    return r"\y" + re.escape(q.strip()) + r"\y"


async def _volume(db, pat: str, days: int) -> tuple[int, int]:
    r = (await db.execute(text("""
        SELECT
          count(*) FILTER (WHERE collected_at > now() - make_interval(days => :d)) AS cur,
          count(*) FILTER (WHERE collected_at > now() - make_interval(days => :d2)
                             AND collected_at <= now() - make_interval(days => :d)) AS prev
          FROM articles
         WHERE collected_at > now() - make_interval(days => :d2) AND title ~* :pat
    """), {"d": days, "d2": days * 2, "pat": pat})).first()
    return (int(r.cur or 0), int(r.prev or 0)) if r else (0, 0)


async def _lean(db, pat: str) -> float | None:
    rows = (await db.execute(text("""
        SELECT stance, count(*) c FROM article_stances
         WHERE actor ~* :pat AND intensity IS NOT NULL GROUP BY stance
    """), {"pat": pat})).fetchall()
    d = {r.stance: int(r.c) for r in rows}
    tot = sum(d.values())
    if not tot:
        return None
    pos = d.get("supportive", 0) + d.get("sympathetic", 0)
    neg = d.get("critical", 0) + d.get("hostile", 0) + d.get("mocking", 0)
    return (pos - neg) / tot


async def _recent_fired(db, watch_id: int, alert_type: str) -> bool:
    n = (await db.execute(text("""
        SELECT count(*) FROM analytics.keyword_alerts
         WHERE watch_id = :w AND alert_type = :t
           AND fired_at > now() - make_interval(hours => :h)
    """), {"w": watch_id, "t": alert_type, "h": COOLDOWN_HOURS})).scalar()
    return int(n or 0) > 0


async def _fire(db, watch_id: int, alert_type: str, payload: dict) -> None:
    await db.execute(text("""
        INSERT INTO analytics.keyword_alerts (watch_id, alert_type, payload)
        VALUES (:w, :t, CAST(:p AS jsonb))
    """), {"w": watch_id, "t": alert_type, "p": json.dumps(payload)})


async def evaluate_watch(db, watch: dict) -> list[str]:
    """Evaluate one watch row; fire alerts as needed. Returns fired types."""
    pat = _word_pattern(watch["keyword"])
    days = int(watch.get("days") or 7)
    fired: list[str] = []

    cur, prev = await _volume(db, pat, days)
    if prev >= 5:
        vpct = (cur - prev) / prev * 100.0
        if vpct >= SPIKE_PCT and not await _recent_fired(db, watch["id"], "spike"):
            await _fire(db, watch["id"], "spike",
                        {"metric": "article_volume", "before": prev, "after": cur,
                         "velocity_pct": round(vpct, 1)})
            fired.append("spike")

    lean = await _lean(db, pat)
    baseline = (watch.get("classification") or {}).get("_lean_baseline") \
        if isinstance(watch.get("classification"), dict) else None
    if lean is not None and baseline is not None:
        if abs(lean - baseline) >= SENTIMENT_FLIP \
                and not await _recent_fired(db, watch["id"], "sentiment_flip"):
            await _fire(db, watch["id"], "sentiment_flip",
                        {"metric": "stance_lean", "before": round(baseline, 3),
                         "after": round(lean, 3)})
            fired.append("sentiment_flip")

    await db.execute(text("""
        UPDATE analytics.keyword_watch SET last_checked_at = now() WHERE id = :w
    """), {"w": watch["id"]})
    return fired


async def evaluate_all(db, limit: int = 200) -> dict[str, Any]:
    """Evaluate all active watches due for a check. Beat-job entry point."""
    rows = (await db.execute(text("""
        SELECT id, keyword, days, classification
          FROM analytics.keyword_watch
         WHERE is_active
           AND (last_checked_at IS NULL
                OR last_checked_at < now() - make_interval(mins => cadence_minutes))
         ORDER BY last_checked_at ASC NULLS FIRST LIMIT :lim
    """), {"lim": limit})).fetchall()
    total = 0
    for r in rows:
        watch = {"id": r.id, "keyword": r.keyword, "days": r.days,
                 "classification": r.classification}
        fired = await evaluate_watch(db, watch)
        total += len(fired)
    await db.commit()
    return {"evaluated": len(rows), "alerts_fired": total}
