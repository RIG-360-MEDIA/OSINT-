#!/usr/bin/env bash
# rig-today-watchdog — so nothing we built on 2026-07-10 ever fails SILENTLY.
#
# Checks, every run:
#   1. the isolated services  rigmedia:8701 (media verify) · riggeo:8700 (satellite) ·
#      rigident:8702 (identity footprint) — /health; auto-`docker start` if down.
#   2. the cookie-dependent keyword collectors reddit/twitter/instagram — a live micro-probe;
#      an expired session ALERTs (cookies can't be auto-fixed; they need a human refresh).
#
# ALERTs go to journald (matching _v9_watchdog.sh). Set NTFY_TOPIC to also push to your
# phone via ntfy.sh — that's what turns "silent for days" into "known in minutes".
#   journalctl -u rig-today-watchdog.service --since -1d | grep ALERT
set -uo pipefail
ts(){ date -u +'%Y-%m-%dT%H:%M:%SZ'; }
NTFY_TOPIC="${NTFY_TOPIC:-}"
declare -a ALERTS=()
alert(){ echo "[$(ts)] ALERT — $*"; ALERTS+=("$*"); }
note(){  echo "[$(ts)] ok — $*"; }

check_svc(){ # name port
  local name="$1" port="$2"
  if curl -fsS -m 8 "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
    note "service ${name} (:${port})"
    return
  fi
  alert "service ${name} (:${port}) DOWN — restarting"
  docker start "${name}" >/dev/null 2>&1
  sleep 5
  if curl -fsS -m 8 "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
    note "service ${name} recovered after restart"
  else
    alert "service ${name} STILL DOWN after restart — needs a human"
  fi
}

check_svc rigmedia 8701
check_svc riggeo   8700
check_svc rigident 8702
check_svc rigscout 8610

# cookie collectors — reddit/twitter/instagram sessions
if probe_out="$(docker exec -w /app -e PYTHONPATH=/app rig-backend python scripts/maintenance/_collector_health.py 2>&1)"; then
  note "keyword collectors reddit/twitter/instagram healthy"
else
  fail_line="$(printf '%s\n' "$probe_out" | grep '^FAIL' | head -1)"
  alert "keyword collectors — ${fail_line:-probe failed} — refresh the session cookie(s) in infrastructure/.env.prod"
fi

# optional phone push so an ALERT is actually seen
if [ "${#ALERTS[@]}" -gt 0 ] && [ -n "$NTFY_TOPIC" ]; then
  printf 'RIG watchdog:\n%s\n' "$(printf '  - %s\n' "${ALERTS[@]}")" \
    | curl -fsS -m 8 -H "Title: RIG watchdog" -H "Priority: high" -d @- "https://ntfy.sh/${NTFY_TOPIC}" >/dev/null 2>&1 || true
fi

[ "${#ALERTS[@]}" -eq 0 ] && echo "[$(ts)] heartbeat — all today's builds healthy"
exit 0
