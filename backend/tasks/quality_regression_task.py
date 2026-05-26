"""Celery task: nightly gold-set regression.

Runs `scripts/audit/gold_regression.py` against the live DB and writes the
output JSON to `/docs/quality/regression_YYYY-MM-DD.json`. The /observe
Quality Monitor panel reads the most recent regression file to surface
drift counts.

Schedule registered in `backend/celery_app.py` beat_schedule:
    "quality-regression-nightly": run daily at 03:00 IST.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from celery import shared_task

logger = logging.getLogger(__name__)

REPO_ROOT = Path("/app")
QUALITY_DIR = Path("/docs/quality") if Path("/docs/quality").exists() else REPO_ROOT / "docs" / "quality"
GOLD_PATH = QUALITY_DIR / "gold_set_v1.jsonl"


@shared_task(
    name="tasks.quality.gold_regression",
    bind=True,
    queue="nlp",
    soft_time_limit=900,
    time_limit=1200,
)
def gold_regression_task(self) -> dict:
    """Run gold_regression.py and return its summary JSON."""
    if not GOLD_PATH.exists():
        logger.error("gold_set_v1.jsonl not found at %s", GOLD_PATH)
        return {"ok": False, "error": "gold_set_not_found"}

    today = datetime.utcnow().strftime("%Y-%m-%d")
    out_path = QUALITY_DIR / f"regression_{today}.json"

    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "audit" / "gold_regression.py"),
        "--gold", str(GOLD_PATH),
        "--out", str(out_path),
    ]
    logger.info("Running gold regression: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if proc.returncode != 0:
        logger.error("gold_regression.py failed: %s", proc.stderr[:2000])
        return {"ok": False, "error": "subprocess_failed",
                "stderr": proc.stderr[:500]}

    try:
        summary = json.loads(out_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "error": f"summary_parse: {exc}"}

    drift_total = sum(int(v) for v in summary.get("drift", {}).values())
    logger.info("Gold regression complete: drift_total=%d", drift_total)
    return {
        "ok": True,
        "date": today,
        "drift_total": drift_total,
        "matched": summary.get("matched"),
        "gold_size": summary.get("gold_size"),
        "summary_path": str(out_path),
    }
