#!/usr/bin/env bash
# In-container stand-in for deploy/crontab, for hosts without cron (free Render tier). Same jobs, same IST times.
# Data loads ("heavy") run one at a time; every other job has its own lock, so quotes, alerts and emails never block each other or a load.
# A job that is still running when its next slot arrives is skipped, not stacked.
# Runs for as long as the container is awake; the keep-alive workflow keeps it awake. Output: /tmp/scheduler.log
set -uo pipefail
cd "${APP_DIR:-/app}"
PY="${PYTHON:-python}"
export TZ=Asia/Kolkata
LIMIT_ARGS=()
[ -n "${INGEST_LIMIT:-}" ] && [ "${INGEST_LIMIT}" != "0" ] && LIMIT_ARGS=(--limit "$INGEST_LIMIT")
log() { echo "$(date '+%F %T') $*"; }

run() {  # run <heavy|light> <name> <args...>: skip if the previous run of the same lock is still going
  local kind="$1" name="$2"; shift 2
  [ "$kind" = "light" ] && kind="$name"
  ( flock -n 9 || { log "skip $name (busy)"; exit 0; }
    log "start $name"; $PY -m finlit.worker "$@" >> "/tmp/job-$name.log" 2>&1; log "done $name rc=$?" ) 9>"/tmp/finlit-$kind.lock" &
}

# First start: universe, the biggest companies first, then as many as INGEST_LIMIT allows. Resumable.
(
  flock 9
  log "start boot-load"
  $PY -m finlit.worker refresh-calendars               # IPO and results calendars first: light, and visible at once
  $PY -m finlit.worker refresh-results                 # anyone who has reported since the last run
  $PY -m finlit.worker refresh-universe
  $PY -m finlit.worker refresh-listing                  # every listed company's price and market cap (skipped if it ran in the last 6 hours)
  $PY -m finlit.worker rebuild-metrics --only-missing   # screener filters for companies loaded before they existed (database only)
  $PY -m finlit.worker refresh-indices                  # NIFTY index membership: also decides which companies load first
  $PY -m finlit.worker prune                            # stay inside the free database's storage: top INGEST_LIMIT + recently opened
  $PY -m finlit.worker ingest RELIANCE TCS INFY HDFCBANK ICICIBANK SBIN ITC LT BHARTIARTL HINDUNILVR
  $PY -m finlit.worker ingest-all "${LIMIT_ARGS[@]}" --parallel 2
  log "done boot-load"
) 9>/tmp/finlit-heavy.lock >> /tmp/job-boot-load.log 2>&1 &

# Stocks opened before they were loaded are prepared in the background.
( while true; do $PY -m finlit.worker drain-queue --loop >> /tmp/job-drain.log 2>&1; sleep 30; done ) &

last=""
while true; do
  now="$(date '+%M %H %u')"; [ "$now" = "$last" ] && { sleep 5; continue; }; last="$now"
  read -r M H D <<< "$now"; H=$((10#$H)); M=$((10#$M)); D=$((10#$D))   # D: 1=Mon .. 7=Sun
  weekday=$(( D >= 1 && D <= 5 )); market=$(( weekday && H >= 9 && H <= 15 ))
  QE="${QUOTES_EVERY_MINUTES:-1}"   # minutes between live-price updates; 10 lets a serverless database (Neon free) sleep between runs
  (( market && M % QE == 0 )) && run light quotes refresh-quotes
  (( market && M % 10 == 0 )) && run light alerts-live check-alerts --kind live
  (( weekday && H == 19 && M == 30 )) && run light alerts-daily check-alerts --kind daily
  (( H == 1 && M == 5 )) && run heavy prune prune
  (( H == 20 && M == 10 )) && run light listing refresh-listing   # nightly, after the close: all ~5,800 companies' prices in two provider calls and one short write, then the database may sleep
  (( H == 3 && M == 10 )) && run light coverage audit-coverage --sample 80 --record   # a rotating sample of the whole market: what the provider sent against what the reports show
  (( H == 1 && M == 30 )) && run heavy ingest ingest-all --hours 20 "${LIMIT_ARGS[@]}" --parallel 2
  (( D == 7 && H == 2 && M == 15 )) && run heavy universe refresh-universe
  (( D == 7 && H == 2 && M == 45 )) && run light indices refresh-indices
  (( H == 6 && M == 45 )) && run light calendars refresh-calendars
  (( H >= 8 && H <= 23 && M == 20 )) && run light results refresh-results   # hourly: companies that have just reported are rebuilt, so their quarter shows within hours
  (( market && M == 5 && H % 3 == 0 )) && run light calendars-day refresh-calendars
  (( weekday && H == 7 && M == 30 )) && run light screens check-screens
  (( D == 7 && H == 18 && M == 30 )) && run light digest send-digest
  sleep 20
done
