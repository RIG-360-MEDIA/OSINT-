"""Idempotently re-enable YouTube clip collection in celery_app.py.

Restores the three lines removed by commit 63de8a8 (2026-05-22):
  1. import   "backend.tasks.youtube_task"
  2. route    "tasks.collect_youtube" -> queue "youtube"
  3. beat      "collect-youtube-every-2h" (timedelta(hours=2))

Anchors on the dict/list openings so it is robust to surrounding drift.
Run: python3 patch_reenable_youtube.py /root/rig/backend/celery_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

IMPORT_LINE = '        "backend.tasks.youtube_task",'
ROUTE_LINE = '            "tasks.collect_youtube": {"queue": "youtube"},'
BEAT_BLOCK = '''            "collect-youtube-every-2h": {
                # Restored 2026-06-05: collection was stripped in 63de8a8
                # (2026-05-22) which silently halted clip ingestion ~05-25.
                # Transcript fetch (~30-60s/video) runs on the dedicated
                # `youtube` queue, so it never blocks other collectors.
                "task": "tasks.collect_youtube",
                "schedule": timedelta(hours=2),
                "options": {"queue": "youtube"},
            },'''


def patch(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    if "youtube" in text.lower():
        print("ABORT: 'youtube' already present in celery_app.py — no change.")
        return 1

    backup = path.with_suffix(path.suffix + ".bak-preyoutube")
    backup.write_text(text, encoding="utf-8")
    print(f"backup written: {backup}")

    lines = text.splitlines(keepends=True)
    out: list[str] = []
    did_import = did_route = did_beat = False

    for line in lines:
        out.append(line)
        stripped = line.strip()
        if stripped == "include=[" and not did_import:
            out.append(IMPORT_LINE + "\n")
            did_import = True
        elif stripped.startswith('"task_routes":') and stripped.endswith("{") and not did_route:
            out.append(ROUTE_LINE + "\n")
            did_route = True
        elif stripped.startswith('"beat_schedule":') and stripped.endswith("{") and not did_beat:
            out.append(BEAT_BLOCK + "\n")
            did_beat = True

    if not (did_import and did_route and did_beat):
        print(
            "FAIL: anchors not all found "
            f"(import={did_import} route={did_route} beat={did_beat}) — no write."
        )
        return 2

    path.write_text("".join(out), encoding="utf-8")
    print("OK: re-inserted import + route + beat entry.")
    return 0


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "backend/celery_app.py")
    raise SystemExit(patch(target))
