"""quality_compare_task.py — Daily new-article-quality vs backfilled-baseline.

Runs at 03:30 IST every day. Computes the same audit metrics as the deep
audit, but scoped to articles ingested in the LAST 24 HOURS. Diffs against
the baseline snapshot taken once after T4 completed.

Output: docs/quality/new-vs-baseline-YYYY-MM-DD.json with:
  {
    "ran_at": iso,
    "window": "last 24h",
    "n_new_articles": int,
    "metrics_today": {...},
    "metrics_baseline": {...},
    "deltas": {metric_name: {today, baseline, ratio, alert}},
    "alerts": ["metric_name regressed 3.2x", ...]
  }

Alert threshold: any metric with `today > 2 * baseline` triggers a string
in `alerts` and a row in `audit_decisions` for follow-up.

Surfaced in /observe Quality Monitor (the helper reads the latest file).
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from celery import shared_task
from sqlalchemy import text

logger = logging.getLogger(__name__)

QUALITY_DIR = (
    Path("/docs/quality") if Path("/docs/quality").exists()
    else Path("docs/quality")
)
BASELINE_PATH = QUALITY_DIR / "new-article-baseline.json"


# ── Metric computation (single query, scoped by collected_at) ────────────────

async def _compute_metrics(db, hours: int) -> dict[str, Any]:
    """Same metrics shape for both today and baseline."""
    sql = """
        WITH new_articles AS (
            SELECT id, collected_at, language_detected, title,
                   summary_executive, labse_embedding, substrate_status,
                   published_at, extraction_version
              FROM articles
             WHERE collected_at >= NOW() - make_interval(hours => :h)
               AND substrate_status = 'ok'
        )
        SELECT
          (SELECT COUNT(*) FROM new_articles) AS n_articles,
          (SELECT COUNT(*) FROM new_articles
            WHERE language_detected='en' AND title ~ '[ఀ-౿]') AS lang_en_telugu,
          (SELECT COUNT(*) FROM new_articles
            WHERE language_detected='en' AND title ~ '[ऀ-ॿ]') AS lang_en_devanagari,
          (SELECT COUNT(*) FROM new_articles
            WHERE LENGTH(summary_executive) = 500) AS cliff_500,
          (SELECT COUNT(*) FROM new_articles
            WHERE LENGTH(summary_executive) = 1000) AS cliff_1000,
          (SELECT COUNT(*) FROM new_articles
            WHERE LENGTH(COALESCE(summary_executive,'')) < 50) AS thin_summary,
          (SELECT COUNT(*) FROM new_articles
            WHERE labse_embedding IS NULL) AS null_embedding,
          (SELECT COUNT(*) FROM article_events ae
            JOIN new_articles a ON a.id = ae.article_id
           WHERE ae.is_future = TRUE
             AND ae.effective_event_date IS NOT NULL
             AND ae.effective_event_date < a.published_at::date - INTERVAL '60 days'
          ) AS is_future_contradictions,
          (SELECT COUNT(*) FROM article_claims ac
            JOIN new_articles a ON a.id = ac.article_id
           WHERE LOWER(ac.subject_text) IN
                 ('article','story','report','piece','news','we','they')
          ) AS placeholder_claims,
          (SELECT COUNT(*) FROM article_claims ac
            JOIN new_articles a ON a.id = ac.article_id) AS total_claims
    """
    row = (await db.execute(text(sql), {"h": int(hours)})).fetchone()
    m = dict(row._mapping)
    # Add derived rates so the alert thresholds are scale-invariant
    total = max(m["n_articles"], 1)
    m["lang_mistag_rate"] = round(
        100.0 * (m["lang_en_telugu"] + m["lang_en_devanagari"]) / total, 3)
    m["cliff_rate"] = round(100.0 * (m["cliff_500"] + m["cliff_1000"]) / total, 3)
    m["thin_summary_rate"] = round(100.0 * m["thin_summary"] / total, 3)
    m["null_embedding_rate"] = round(100.0 * m["null_embedding"] / total, 3)
    m["placeholder_rate"] = round(
        100.0 * m["placeholder_claims"] / max(m["total_claims"], 1), 3)
    m["is_future_rate"] = round(
        100.0 * m["is_future_contradictions"] / total, 3)
    return m


# ── Diff + alert logic ───────────────────────────────────────────────────────

# Metrics tracked for regression — keyed by rate, not raw count
ALERTABLE_RATES = (
    "lang_mistag_rate",
    "cliff_rate",
    "thin_summary_rate",
    "null_embedding_rate",
    "placeholder_rate",
    "is_future_rate",
)
ALERT_RATIO = 2.0
ABSOLUTE_FLOOR = 0.5  # ignore alerts where baseline rate is already < 0.5%


def _diff(today: dict[str, Any], baseline: dict[str, Any]) -> tuple[dict, list[str]]:
    deltas: dict[str, dict[str, Any]] = {}
    alerts: list[str] = []
    for k in ALERTABLE_RATES:
        t = float(today.get(k, 0))
        b = float(baseline.get(k, 0))
        ratio = (t / b) if b > 0 else (0.0 if t == 0 else float("inf"))
        alert = (b >= ABSOLUTE_FLOOR or t >= ABSOLUTE_FLOOR) and ratio > ALERT_RATIO
        deltas[k] = {
            "today": t, "baseline": b,
            "ratio": round(ratio, 2) if ratio != float("inf") else "inf",
            "alert": alert,
        }
        if alert:
            alerts.append(f"{k} regressed {ratio:.1f}x (today {t}%, baseline {b}%)")
    return deltas, alerts


# ── Persistence + audit-queue write-back ─────────────────────────────────────

async def _write_audit_decision(db, alert_text: str) -> None:
    """Drop a row into audit_decisions so the AuditQueue panel surfaces it."""
    try:
        await db.execute(text("""
            INSERT INTO audit_decisions
                (article_id, field_name, extraction_version, verdict, note)
            VALUES ('00000000-0000-0000-0000-000000000000', :field, 0,
                    'unsure', :note)
            ON CONFLICT (article_id, field_name, extraction_version)
            DO UPDATE SET note = EXCLUDED.note, decided_at = NOW()
        """), {"field": "quality_alert", "note": alert_text[:500]})
    except Exception as exc:
        logger.warning("Could not write audit alert: %s", exc)


# ── Main flow ────────────────────────────────────────────────────────────────

async def _run() -> dict[str, Any]:
    from backend.database import get_db
    today = datetime.utcnow().strftime("%Y-%m-%d")
    QUALITY_DIR.mkdir(parents=True, exist_ok=True)
    out_path = QUALITY_DIR / f"new-vs-baseline-{today}.json"

    # Load baseline (may not exist yet — first run after T4 will create it)
    baseline: dict[str, Any] | None = None
    if BASELINE_PATH.exists():
        try:
            baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not parse baseline: %s", exc)

    async with get_db() as db:
        metrics_today = await _compute_metrics(db, hours=24)
        result: dict[str, Any] = {
            "ran_at": datetime.utcnow().isoformat() + "Z",
            "window_hours": 24,
            "n_new_articles": metrics_today["n_articles"],
            "metrics_today": metrics_today,
            "metrics_baseline": baseline,
            "deltas": {},
            "alerts": [],
        }
        if baseline:
            deltas, alerts = _diff(metrics_today, baseline)
            result["deltas"] = deltas
            result["alerts"] = alerts
            for a in alerts:
                await _write_audit_decision(db, a)
            await db.commit()

    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    logger.info("quality_compare: wrote %s; alerts=%d", out_path, len(result["alerts"]))
    return result


@shared_task(
    name="tasks.quality.compare",
    bind=True,
    queue="nlp",
    soft_time_limit=300,
    time_limit=600,
)
def quality_compare_task(self) -> dict[str, Any]:
    """Daily Celery task — wired in celery_app.py beat_schedule."""
    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("quality_compare failed: %s", exc)
        return {"error": str(exc)[:200]}
