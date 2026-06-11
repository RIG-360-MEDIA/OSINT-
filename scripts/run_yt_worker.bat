@echo off
REM ============================================================
REM YouTube residential transcript worker — runs on THIS laptop
REM ============================================================
REM Fetches captions from YouTube (residential IP, not blocked)
REM and marks rows 'transcribed' so Hetzner can extract clips.
REM
REM STEP 1: open an SSH tunnel to Hetzner Postgres in a NEW terminal:
REM   ssh -i %USERPROFILE%\.ssh\rig_hetzner -N -L 5433:rig-postgres:5432 root@178.105.63.154
REM
REM STEP 2: run THIS script (keep the tunnel open while it runs).
REM
REM The script drains pending rows, fetches transcripts, updates DB.
REM It loops forever — Ctrl+C to stop.
REM ============================================================

cd /d "%~dp0\.."

REM Postgres via SSH tunnel (localhost:5433 → Hetzner rig-postgres:5432)
set YOUTUBE_WORKER_DB_URL=postgresql+asyncpg://rig:rigpassword@127.0.0.1:5433/rig

REM Fetch 3 videos per tick, 5s pause between each, 30s idle sleep
set YOUTUBE_WORKER_BATCH=3
set YOUTUBE_WORKER_SLEEP=5
set YOUTUBE_WORKER_IDLE=30
set YOUTUBE_WORKER_MAX_ATTEMPTS=4

REM Do NOT set YT_RELAY_URL — worker fetches directly from residential IP
set YT_RELAY_URL=

echo Starting YouTube transcript worker...
echo DB: %YOUTUBE_WORKER_DB_URL%
echo Batch=%YOUTUBE_WORKER_BATCH%  Sleep=%YOUTUBE_WORKER_SLEEP%s  Idle=%YOUTUBE_WORKER_IDLE%s
echo.
echo Press Ctrl+C to stop.
echo.

python -m backend.collectors.youtube_v2.worker
