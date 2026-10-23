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

# Free memory of this container in MB: its memory limit minus what it uses, not counting page cache the kernel can drop (cgroup v2, then v1;
# without a limit, the machine's MemAvailable). The free plan has 512 MB for the web server, the site backend and every job together.
free_mb() {
  local max cur inactive
  if [ -r /sys/fs/cgroup/memory.max ]; then
    max="$(cat /sys/fs/cgroup/memory.max)"; cur="$(cat /sys/fs/cgroup/memory.current)"
    inactive="$(awk '$1 == "inactive_file" {print $2}' /sys/fs/cgroup/memory.stat 2>/dev/null)"
  elif [ -r /sys/fs/cgroup/memory/memory.limit_in_bytes ]; then
    max="$(cat /sys/fs/cgroup/memory/memory.limit_in_bytes)"; cur="$(cat /sys/fs/cgroup/memory/memory.usage_in_bytes)"
    inactive="$(awk '$1 == "total_inactive_file" {print $2}' /sys/fs/cgroup/memory/memory.stat 2>/dev/null)"
  fi
  if [ -n "${max:-}" ] && [ "$max" != "max" ] && [ "${#max}" -lt 16 ]; then   # a real limit (an "unlimited" v1 limit is a 19-digit number)
    echo $(( (max - cur + ${inactive:-0}) / 1048576 ))
  else
    awk '/^MemAvailable:/ {print int($2 / 1024)}' /proc/meminfo 2>/dev/null || echo 99999
  fi
}
MIN_FREE_MB="${SCHED_MIN_FREE_MB:-120}"         # other jobs (quotes, alerts, emails, loads) start only with this much free
FUNDS_MIN_FREE_MB="${SCHED_FUNDS_MIN_FREE_MB:-180}"   # fund jobs: the largest measured one peaks at 174 MB (ETF refresh)

run() {  # run <heavy|light> <name> <args...>: skip if the previous run of the same lock is still going, or if memory is short
  local kind="$1" name="$2"; shift 2
  [ "$kind" = "light" ] && kind="$name"
  ( flock -n 9 || { log "skip $name (busy)"; exit 0; }
    free="$(free_mb)"; [ "$free" -lt "$MIN_FREE_MB" ] && { log "skip $name (only ${free} MB free)"; exit 0; }
    log "start $name"; $PY -m finlit.worker "$@" >> "/tmp/job-$name.log" 2>&1; log "done $name rc=$?" ) 9>"/tmp/finlit-$kind.lock" &
}

# Fund data jobs (ETF and mutual fund loads, 117-174 MB each) take turns on one lock: a job that finds another running waits for it
# (up to 3 hours) instead of running beside it or being dropped, then waits (up to 20 minutes) for enough free memory.
FUNDS_LOCK=/tmp/finlit-funds.lock
wait_memory() {  # wait_memory <name>: 0 once enough memory is free, 1 after 20 minutes without
  local free
  for _ in $(seq 1 40); do
    free="$(free_mb)"; [ "$free" -ge "$FUNDS_MIN_FREE_MB" ] && return 0
    sleep 30
  done
  log "skip $1 (only ${free} MB free after waiting 20 minutes)"; return 1
}
run_funds() {  # run_funds <name> <args...>
  local name="$1"; shift
  ( flock -w 10800 9 || { log "skip $name (fund jobs busy for 3 hours)"; exit 0; }
    wait_memory "$name" || exit 0
    log "start $name"; MALLOC_ARENA_MAX=2 $PY -m finlit.worker "$@" >> "/tmp/job-$name.log" 2>&1; log "done $name rc=$?" ) 9>"$FUNDS_LOCK" &
}

# Waits (up to 10 minutes) until the web server answers, so the loads below never compete with it while it starts.
wait_web() {
  for _ in $(seq 1 120); do
    $PY -c "import sys,urllib.request; urllib.request.urlopen('http://127.0.0.1:${PORT:-8000}/api/health', timeout=3)" >/dev/null 2>&1 && return 0
    sleep 5
  done
  return 1
}

# One step of the ETF / mutual fund load: run it, log ONE line with its result, and report failure so the next step is not started.
fund_step() {  # fund_step <label> <worker args...>: takes its turn on the fund jobs' lock, like the nightly runs
  local label="$1"; shift
  local out rc
  exec 8>"$FUNDS_LOCK"; flock -w 10800 8 || { log "$label skipped: fund jobs busy for 3 hours"; exec 8>&-; return 1; }
  if ! wait_memory "$label"; then exec 8>&-; return 1; fi
  out="$(MALLOC_ARENA_MAX=2 $PY -m finlit.worker "$@" 2>&1)"; rc=$?
  exec 8>&-
  log "$label rc=$rc $(printf '%s' "$out" | tail -n 1 | cut -c1-300)"
  return $rc
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
  # ETFs, then funds, then 5 years of fund history: strictly one after the other, each only if the one before it worked, and only once the web server is up.
  # Each is resumable (the fund history skips fund houses already done) and none of them runs on a timer, so a restart loses nothing and the database may sleep.
  if wait_web; then
    fund_step boot-instruments refresh-instruments --max-age-hours 20   # Dhan's public instrument file first: the ETF job reads its ETF list from it
    if fund_step boot-etf refresh-etf --max-age-hours 12 --resume && fund_step boot-mf refresh-mf --max-age-hours 12; then
      fund_step boot-facts refresh-facts --max-age-hours 20    # fund size, expense ratios, launch dates (AMFI); its result never stops the history load
      [ -n "${DHAN_CLIENT_ID:-}" ] && fund_step boot-dhan-check dhan-check      # only when Dhan is set up: proves the credentials; the result is at /api/mf/status (run:dhan-check)
      fund_step boot-mf-history backfill-mf
    fi
  else
    log "boot-etf skipped: the web server did not answer within 10 minutes"
  fi
  $PY -m finlit.worker ingest RELIANCE TCS INFY HDFCBANK ICICIBANK SBIN ITC LT BHARTIARTL HINDUNILVR
  $PY -m finlit.worker ingest-all "${LIMIT_ARGS[@]}" --parallel 2
  # fund holdings and exit loads (fund houses' monthly portfolios, AMFI scheme details): last, so stock loads come first; waits its turn with the other fund jobs; skipped if it ran in the last 20 hours
  flock -w 10800 "$FUNDS_LOCK" env MALLOC_ARENA_MAX=2 $PY -m finlit.worker refresh-portfolios --max-age-hours 20 >> /tmp/job-portfolios.log 2>&1
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
  (( weekday && H == 20 && M == 40 )) && run_funds etf refresh-etf    # nightly after the close: ETF prices and history (Upstox), paced (ETF_CALLS_PER_MINUTE)
  (( weekday && ((H == 22 && M == 10) || (H == 23 && M == 40)) )) && run_funds etf-retry refresh-etf --resume   # retries: only the ETFs the nightly run could not fetch (none left = no provider calls)
  (( H == 21 && M == 10 )) && run_funds mf refresh-mf                 # nightly: AMFI publishes the day's NAVs in the evening
  (( H == 23 && M == 30 )) && run_funds mf-late refresh-mf            # again after AMFI's 11 pm deadline: most fund houses publish after 21:10, so this run brings the day's NAVs
  (( H == 7 && M == 50 )) && run_funds instruments refresh-instruments   # daily before the open: Dhan's public instrument file (new listings and ETFs, surveillance changes, F&O additions)
  (( H == 21 && M == 40 )) && run_funds facts refresh-facts           # nightly, after the NAVs: fund size (quarterly average AUM), expense ratios, launch dates (AMFI)
  (( H == 4 && M == 40 )) && run_funds portfolios refresh-portfolios   # holdings and exit loads: fund-house files only when a new month is out (files already read are skipped)
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
