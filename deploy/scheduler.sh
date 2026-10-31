#!/usr/bin/env bash
# In-container background processes, started by start.sh (deploy/render-start.sh) with nohup. Output: /tmp/scheduler.log
#
# ALL scheduling of data jobs now lives in ONE Python process, the job supervisor (backend/finlit/jobs, `python -m finlit.worker supervise`, docs/JOBS.md):
# what is due (SLA, quiet windows, intervals), the order (priority; bulk jobs strictly one at a time), memory/CPU gating, the watchdog, retries after
# 30 / 60 / 120 minutes, the admin pause with its expiry, and the status at GET /api/jobs/status. This file only keeps three long-running things alive:
#   1. the supervisor itself (restarted with a growing delay if it ever exits; a second copy is refused by its Redis lock),
#   2. the on-demand lane `drain-queue --loop` (builds a stock a visitor opened before it was loaded; outside every gate, switch and lock),
#   3. the commodity price loop (when a commodity source is configured).
# DECISION: the old per-minute light loops (live quotes, member alerts, results every hour) are registry jobs too, not bash: they are then memory-gated,
# recorded in job_runs, visible in the status and retried like every other job; bash had none of that. Nothing time-driven is left in this file.
# OBSOLETE and removed (see git history before the supervisor): the exact-minute `due` slots, the DB windows (Neon), `run`/`run_funds`/`fund_step`, the boot chain,
# the Prism loop, the heavy/bulk/funds flock files and the loads_paused shell helpers.
set -uo pipefail
cd "${APP_DIR:-/app}"
PY="${PYTHON:-python}"
export TZ=Asia/Kolkata
log() { echo "$(date '+%F %T') $*"; }

# 1. The supervisor. Exit code 3 = another supervisor holds the lock (normal during a very fast restart): wait, then try again.
(
  delay=5
  while true; do
    started=$(date +%s)
    log "supervisor: starting"
    $PY -m finlit.worker supervise 2>&1 | tee -a /tmp/job-supervisor.log   # also reaches `docker compose logs app`
    rc=${PIPESTATUS[0]}
    ran=$(( $(date +%s) - started ))
    if [ "$rc" = 3 ]; then delay=30; elif [ "$ran" -ge 300 ]; then delay=5; else delay=$(( delay * 2 > 300 ? 300 : delay * 2 )); fi
    log "supervisor: exited rc=$rc after ${ran}s; restarting in ${delay}s"
    sleep "$delay"
  done
) &

# 2. Stocks opened before they were loaded are prepared at once. Waits on a Redis flag (no Postgres query while idle); if it exits, it restarts in 10 seconds
# (a visitor may be waiting). Always on, normal priority, outside every lock, memory gate and admin switch.
( while true; do $PY -m finlit.worker drain-queue --loop >> /tmp/job-drain.log 2>&1; sleep 10; done ) &

# 3. Commodity prices: MCX futures (Dhan) every 10 seconds while MCX trades, international prices every minute, into Redis. Started only when at least one source is
# set up; COMMODITIES_WORKER=0 switches it off. About 62 MB resident.
if [ "${COMMODITIES_WORKER:-1}" != "0" ] && [ -n "${DHAN_CLIENT_ID:-}${METALS_DEV_API_KEY:-}${METALPRICEAPI_KEY:-}" ]; then
  ( while true; do $PY -m finlit.worker refresh-commodities --loop >> /tmp/job-commodities.log 2>&1; sleep 120; done ) &
fi

wait
