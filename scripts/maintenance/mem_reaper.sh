#!/bin/sh
# mem_reaper.sh — no-redeploy stopgap for the Playwright Chrome memory leak.
# Runs every 10 min on the Hetzner host (cron). Two jobs:
#   1. Cap the leak — kill Chrome in rig-backend if its total RSS > 4096 MB,
#      or emergency-kill if host available RAM drops < 600 MB. The reaper only
#      fires when Chrome is bloated, so it does not interrupt normal scraping.
#   2. Re-assert the OOM shield — oom_score_adj resets on a container restart,
#      so we re-apply Postgres=-900 (un-killable) and backend-init=-500 every
#      run; the OOM victim can then only ever be a recyclable Chrome/worker.
# Remove once the durable fix ships: Playwright browser.close() + reuse,
# celery --max-memory-per-child, and persistent compose oom_score_adj/mem_limit.
LOG=/var/log/mem-reaper.log
ts() { date '+%Y-%m-%d %H:%M:%S'; }

CHROME_MB=$(docker exec rig-backend sh -c "ps -eo rss,args 2>/dev/null | grep '[c]hrome' | awk '{s+=\$1} END{print int(s/1024)}'" 2>/dev/null)
CHROME_MB=${CHROME_MB:-0}
AVAIL=$(free -m | awk '/Mem:/{print $7}')
AVAIL=${AVAIL:-9999}

if [ "$CHROME_MB" -gt 4096 ] || [ "$AVAIL" -lt 600 ]; then
  docker exec rig-backend sh -c "ps -eo pid,args 2>/dev/null | grep '[c]hrome' | awk '{print \$1}' | xargs -r kill -9" 2>/dev/null
  echo "$(ts) reaped chrome (rss=${CHROME_MB}MB avail=${AVAIL}MB)" >> "$LOG"
fi

PG=$(docker inspect -f '{{.State.Pid}}' rig-postgres 2>/dev/null)
BE=$(docker inspect -f '{{.State.Pid}}' rig-backend 2>/dev/null)
if [ -n "$PG" ] && [ -e "/proc/$PG/oom_score_adj" ]; then
  echo -900 > "/proc/$PG/oom_score_adj" 2>/dev/null
  for c in $(pgrep -P "$PG" 2>/dev/null); do echo -900 > "/proc/$c/oom_score_adj" 2>/dev/null; done
fi
if [ -n "$BE" ] && [ -e "/proc/$BE/oom_score_adj" ]; then
  echo -500 > "/proc/$BE/oom_score_adj" 2>/dev/null
fi
