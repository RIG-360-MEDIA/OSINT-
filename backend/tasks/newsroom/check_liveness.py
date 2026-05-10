"""
Channel liveness probe.

Every 5 minutes (via beat), this task hits each `is_live_24x7=TRUE`
channel's `https://www.youtube.com/@<handle>/live` URL through yt-dlp
to discover whether the channel is currently streaming. When yes, we
record the live video id + title; when no, we clear the live id but
preserve `last_live_at` so the UI can show "last live N hours ago".

The probe goes through the same YOUTUBE_PROXY_URL chain that audio
download uses — so liveness check requires the SOCKS proxy to your
laptop / Tailscale exit to be live. If the proxy is down the probe
fails silently and the columns stay stale; this is acceptable
because the WALL UI gracefully handles stale data.

Routed to `whisper` queue but light-weight (a few HTTP calls per
channel). Throttled by the global `_youtube_throttle` so we don't
spike YT requests when many channels are configured.
"""
from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

from backend.celery_app import app
from backend.tasks.newsroom._youtube_throttle import (
    record_block,
    record_success,
    throttle_sync,
    YoutubeCircuitOpen,
)

logger = logging.getLogger(__name__)


def _pg_url() -> str:
    return os.environ.get(
        "DATABASE_URL_SYNC",
        "postgresql://rig:rigpassword@rig-postgres:5432/rig",
    )


@app.task(
    name="tasks.newsroom.check_liveness",
    queue="whisper",
    max_retries=0,
    soft_time_limit=300,
)
def check_liveness() -> dict:
    """Probe each 24×7 channel and update its liveness columns."""
    conn = psycopg2.connect(_pg_url())
    conn.autocommit = True
    stats = {"checked": 0, "live": 0, "not_live": 0, "errors": 0}

    cookies = os.getenv("YOUTUBE_COOKIES_PATH", "").strip()
    proxy = os.getenv("YOUTUBE_PROXY_URL", "").strip()

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, name, yt_handle
                  FROM newsroom_channels
                 WHERE active = TRUE AND is_live_24x7 = TRUE
                """
            )
            channels = cur.fetchall()

        for ch in channels:
            stats["checked"] += 1
            try:
                throttle_sync()
            except YoutubeCircuitOpen as exc:
                logger.info("liveness: %s; abort sweep", exc)
                stats["errors"] += 1
                break

            handle = ch["yt_handle"].lstrip("@")
            url = f"https://www.youtube.com/@{handle}/live"
            cmd = [
                "yt-dlp", "--no-playlist",
                "--quiet", "--no-warnings",
                "--skip-download",
                "--socket-timeout", "10",
                "--print", "%(id)s|||%(title)s",
            ]
            if cookies and os.path.exists(cookies):
                cmd.extend(["--cookies", cookies])
            if proxy:
                cmd.extend(["--proxy", proxy])
            cmd.append(url)

            try:
                result = subprocess.run(
                    cmd, check=True, capture_output=True, text=True, timeout=20,
                )
                line = (result.stdout or "").strip().splitlines()[0] if result.stdout else ""
                if "|||" in line:
                    vid, title = line.split("|||", 1)
                else:
                    vid, title = line, ""

                # YT serves the channel page when no live broadcast exists; the
                # video_id then matches the channel's vanity url not a video.
                # A genuine live id is 11 chars; channel url variants are longer.
                is_live = bool(vid) and len(vid) == 11

                if is_live:
                    record_success()
                    stats["live"] += 1
                    with conn.cursor() as up:
                        up.execute(
                            """
                            UPDATE newsroom_channels
                               SET current_live_video_id = %s,
                                   current_live_title = %s,
                                   last_live_at = NOW(),
                                   last_live_check_at = NOW()
                             WHERE id = %s
                            """,
                            (vid, title[:240] if title else None, ch["id"]),
                        )
                    logger.info("liveness: %s LIVE — %s (%s)", ch["name"], title[:80], vid)
                else:
                    stats["not_live"] += 1
                    with conn.cursor() as up:
                        up.execute(
                            """
                            UPDATE newsroom_channels
                               SET current_live_video_id = NULL,
                                   current_live_title = NULL,
                                   last_live_check_at = NOW()
                             WHERE id = %s
                            """,
                            (ch["id"],),
                        )
                    logger.info("liveness: %s not currently live", ch["name"])
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                stats["errors"] += 1
                err_text = ""
                if isinstance(exc, subprocess.CalledProcessError):
                    err_text = (exc.stderr or "").lower()
                if "sign in" in err_text or "ip block" in err_text:
                    record_block()
                # Probe failure → clear current_live but DON'T touch
                # last_live_at so the UI can keep showing the most recent
                # success.
                with conn.cursor() as up:
                    up.execute(
                        """
                        UPDATE newsroom_channels
                           SET current_live_video_id = NULL,
                               current_live_title = NULL,
                               last_live_check_at = NOW()
                         WHERE id = %s
                        """,
                        (ch["id"],),
                    )
                logger.info("liveness: %s probe failed (%s)", ch["name"], type(exc).__name__)

        return stats
    finally:
        conn.close()
