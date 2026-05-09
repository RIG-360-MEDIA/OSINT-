"""
Phase 4 — live channel monitor.

For each active 24×7 channel, one long-running task pulls 30-second
HLS windows from the live stream and pushes them through the Phase 2
pipeline (process_broadcast in sync mode).

Coordination: Postgres advisory lock keyed by hashtext(channel_id).
Holding the lock = "I am the live_monitor for this channel."
- If a duplicate monitor is enqueued, it tries pg_try_advisory_lock,
  fails immediately, exits cleanly. No second-monitor risk.
- The lock is connection-scoped — if the worker dies, postgres
  releases the lock automatically and the next 5-min beat tick
  re-enqueues a fresh monitor.

`enqueue_live_monitors` is the beat-driven gatekeeper: every 5 min
it scans newsroom_channels WHERE active AND is_live_24x7 and fires
one `live_monitor.delay(channel_id)` per row. Duplicate fires lose
the advisory lock race and exit harmlessly.

Each monitor runs at most `max_runtime_sec` (default: 60 minutes)
before self-terminating, releasing the lock, and letting the next
beat tick respawn a fresh one. This bounds the failure blast radius.
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

from backend.celery_app import app
from backend.tasks.newsroom.process_broadcast import process_broadcast

logger = logging.getLogger(__name__)


def _pg_url() -> str:
    return os.environ.get(
        "DATABASE_URL_SYNC",
        "postgresql://rig:rigpassword@rig-postgres:5432/rig",
    )


_DEFAULT_MAX_RUNTIME_SEC = 60 * 60       # 1 hour per monitor task
_WINDOW_SEC = 30                          # 30-second HLS pulls


@app.task(
    name="tasks.newsroom.enqueue_live_monitors",
    queue="whisper",
)
def enqueue_live_monitors() -> dict:
    """Beat-driven: ensure one live_monitor per active 24×7 channel.

    Duplicate fires lose the advisory lock race and exit. Safe to
    run on every 5-min tick.
    """
    conn = psycopg2.connect(_pg_url())
    fired = 0
    skipped = 0
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, name
                  FROM newsroom_channels
                 WHERE active = TRUE AND is_live_24x7 = TRUE
                """
            )
            channels = cur.fetchall()

        for ch in channels:
            try:
                live_monitor.apply_async(args=[str(ch["id"])])
                fired += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "enqueue_live_monitors: failed to fire %s (%s): %s",
                    ch["name"], ch["id"], exc,
                )
                skipped += 1
        return {"fired": fired, "skipped": skipped, "total_channels": len(channels)}
    finally:
        conn.close()


@app.task(
    name="tasks.newsroom.live_monitor",
    queue="whisper",
    bind=True,
    max_retries=0,                        # never auto-retry — beat respawns
    soft_time_limit=_DEFAULT_MAX_RUNTIME_SEC + 120,
)
def live_monitor(
    self,
    channel_id: str,
    *,
    max_runtime_sec: int = _DEFAULT_MAX_RUNTIME_SEC,
) -> dict:
    """Long-running task: pull 30-s HLS windows from the channel's
    current live stream and push each through process_broadcast.

    Acquires a pg advisory lock keyed on the channel id; another
    monitor for the same channel will lose the race and exit.
    """
    started = time.time()
    stats: dict = {
        "channel_id": channel_id,
        "windows_processed": 0,
        "windows_failed": 0,
        "elapsed_sec": 0.0,
        "lock_acquired": False,
        "exit_reason": None,
    }
    monitor_id = str(uuid.uuid4())[:8]

    # Each monitor uses a dedicated connection so the advisory lock
    # is held for the lifetime of the monitor only.
    conn = psycopg2.connect(_pg_url())
    conn.autocommit = True

    try:
        # ── Acquire advisory lock ─────────────────────────────────────────
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_try_advisory_lock(hashtext(%s)::bigint)",
                (channel_id,),
            )
            (got_lock,) = cur.fetchone()
        if not got_lock:
            stats["exit_reason"] = "lock_busy"
            stats["elapsed_sec"] = time.time() - started
            logger.info(
                "live_monitor[%s] %s: lock busy — another monitor active",
                monitor_id, channel_id,
            )
            return stats
        stats["lock_acquired"] = True

        # ── Resolve channel metadata ──────────────────────────────────────
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT name, yt_handle, language FROM newsroom_channels "
                "WHERE id = %s AND active = TRUE",
                (channel_id,),
            )
            ch = cur.fetchone()
        if not ch:
            stats["exit_reason"] = "channel_inactive"
            stats["elapsed_sec"] = time.time() - started
            return stats

        deadline = started + max_runtime_sec
        prev_video_id: str | None = None

        # ── Stream loop ───────────────────────────────────────────────────
        while time.time() < deadline:
            # Re-check channel is still active each iter (cheap; cuts a
            # dead monitor when the user toggles a channel off)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT active FROM newsroom_channels WHERE id = %s",
                    (channel_id,),
                )
                row = cur.fetchone()
            if not row or not row[0]:
                stats["exit_reason"] = "channel_deactivated"
                break

            # Resolve the current live yt_video_id for the handle
            video_id = _current_live_video_id(ch["yt_handle"])
            if not video_id:
                logger.info(
                    "live_monitor[%s] %s: no live stream resolvable; sleeping 60s",
                    monitor_id, ch["name"],
                )
                time.sleep(60)
                continue

            # Pull the next 30-second window through the pipeline
            try:
                process_broadcast.apply(   # SYNC call within this worker
                    args=[video_id, channel_id],
                    kwargs={
                        "language": ch["language"],
                        "title": ch["name"],
                        "is_live": True,
                        "max_duration_sec": _WINDOW_SEC,
                    },
                ).get(disable_sync_subtasks=False)
                stats["windows_processed"] += 1
            except Exception as exc:  # noqa: BLE001
                stats["windows_failed"] += 1
                logger.warning(
                    "live_monitor[%s] %s: window failed: %s",
                    monitor_id, ch["name"], exc,
                )
                # Brief backoff before next attempt; helps avoid
                # hot-looping when YouTube transiently rejects us
                time.sleep(5)
                continue

            # If yt_video_id changed mid-stream (a new live broadcast
            # rolled in) we just continue the loop with the new id
            if prev_video_id and video_id != prev_video_id:
                logger.info(
                    "live_monitor[%s] %s: live video_id rotated %s -> %s",
                    monitor_id, ch["name"], prev_video_id, video_id,
                )
            prev_video_id = video_id

        stats["exit_reason"] = stats["exit_reason"] or "deadline"
        return stats

    except Exception as exc:  # noqa: BLE001
        logger.exception("live_monitor crashed for %s", channel_id)
        stats["exit_reason"] = f"crash: {exc}"
        return stats
    finally:
        # Release the advisory lock explicitly. (Closing the connection
        # would also release it, but explicit is safer for log clarity.)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_advisory_unlock(hashtext(%s)::bigint)",
                    (channel_id,),
                )
        except Exception:  # noqa: BLE001
            pass
        conn.close()
        stats["elapsed_sec"] = time.time() - started
        logger.info("live_monitor[%s] %s exited: %s", monitor_id, channel_id, stats)


def _current_live_video_id(yt_handle: str) -> str | None:
    """Resolve the currently-live video id for a channel handle.

    Strategy: yt-dlp --get-id on the channel's /live URL returns the
    yt_video_id of whatever is currently streaming, or fails if the
    channel isn't live right now.
    """
    handle = yt_handle.lstrip("@")
    url = f"https://www.youtube.com/@{handle}/live"
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--no-playlist",
                "--quiet", "--no-warnings",
                "--skip-download",
                "--print", "%(id)s",
                url,
            ],
            check=True, capture_output=True, text=True, timeout=20,
        )
        return (result.stdout or "").strip() or None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
