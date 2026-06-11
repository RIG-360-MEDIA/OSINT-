"""snapshot_baseline.py — One-shot baseline capture.

Run this AFTER T4 (placeholder backfill) completes. It computes the same
metrics that `tasks.quality.compare` will compute daily, and writes them
to docs/quality/new-article-baseline.json. The daily comparator then
treats this as ground truth.

Usage (inside rig-backend):
    docker exec rig-backend python /app/scripts/quality/snapshot_baseline.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/app")

from backend.database import get_db  # noqa: E402
from backend.tasks.quality_compare_task import _compute_metrics  # noqa: E402

QUALITY_DIR = (
    Path("/docs/quality") if Path("/docs/quality").exists()
    else Path("docs/quality")
)


async def main() -> int:
    QUALITY_DIR.mkdir(parents=True, exist_ok=True)
    out_path = QUALITY_DIR / "new-article-baseline.json"

    async with get_db() as db:
        # 72h window so we capture a representative sample including a full
        # weekday + weekend day, with T1/T2/T3/T4 already applied
        m = await _compute_metrics(db, hours=72)
    payload = {
        "captured_at": datetime.utcnow().isoformat() + "Z",
        "window_hours": 72,
        **m,
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {out_path}")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
