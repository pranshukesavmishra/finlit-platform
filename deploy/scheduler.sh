#!/usr/bin/env bash
# In-container stand-in for deploy/crontab, for hosts without cron (free Render tier). Same jobs, same IST times.
# Data loads ("heavy") run one at a time; every other job has its own lock, so quotes, alerts and emails never block each other or a load.
# A job that is still running when its next slot arrives is skipped, not stacked.
# Runs for as long as the container is awake; the keep-alive workflow keeps it awake. Output: /tmp/scheduler.log
#
# DB WINDOWS. The database (Neon free plan) suspends 5 minutes after its last query and the plan allows a fixed number of compute hours a month, so
# anything that touches Postgres on a short timer keeps it awake around the clock and uses the month's hours in about 17 days. Therefore:
#   * the data jobs run in a few "DB windows" a day (night 01:00, morning 06:45, after the close 15:50 on weekdays, technical views 18:30 on weekdays, evening 19:10 and 21:10, late 23:30 IST):
#     each window is one chain of jobs, one after the other, so the database wakes a handful of times a day and sleeps in between;
#   * the few jobs outside a window run only while a visitor is on the site (Redis key last-visit, set by the web app: see backend/finlit/wake.py), or, for
#     member price alerts, every 15 minutes in market hours and only if an alert or watchlist target exists (Redis flag, refreshed in every window);
#   * the loops (waiting for opened-but-unloaded stocks, commodity prices into Redis) do not query Postgres while idle.
# The wake budget (estimated wakes today, compute hours this month) is kept in Redis by the worker and shown in the admin Data health tab.
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
# The admin switch "Heavy data loads" (site header > System) is kept in the database; `worker switch-get loads` prints 1 (on) or 0 (paused), and 0
# also when the database cannot be read. The env switches BOOT_LOAD_ENABLED and FUND_LOADS_ENABLED still apply on top: either one off = paused.
loads_paused() {
  [ "$($PY -m finlit.worker switch-get loads 2>/dev/null | tail -n 1)" = 1 ] && return 1
  return 0
}
# The light results jobs (calendars, results, results-light) are paused only by an admin's explicit "off", never by a database that was slow or refusing
# for a moment (a failing read counts as "paused" for the bulk loads above, which skipped the results jobs for no reason when the box was busy).
loads_paused_explicit() {
  [ "$($PY -m finlit.worker switch-get loads-explicit 2>/dev/null | tail -n 1)" = 0 ] && return 0
  return 1
}
MIN_FREE_MB="${SCHED_MIN_FREE_MB:-120}"         # other jobs (quotes, alerts, emails, loads) start only with this much free
RESULTS_MIN_FREE_MB="${SCHED_RESULTS_MIN_FREE_MB:-60}"  # the light results jobs need far less than a load and must not be skipped for want of memory the bulk jobs are using
BULK_LOCK=/tmp/finlit-bulk.lock                         # the CPU-heavy bulk jobs (technicals, Prism pre-compute, score-mf) take turns on this one lock; results, quotes and visitors never wait for it
BULK_WAIT_S="${SCHED_BULK_WAIT_S:-1800}"
FUNDS_MIN_FREE_MB="${SCHED_FUNDS_MIN_FREE_MB:-180}"   # fund jobs: the largest measured one peaks at 174 MB (ETF refresh)

# A skipped results job leaves a one-line reason in Redis (no database), shown at /api/results/status as lastSkipped; the same line goes to the log.
skipped() { log "skip $1 (${2#skipped: })"; case "$1" in calendars*|results*|technicals*) $PY -m finlit.wake note "$1" "$2" >/dev/null 2>&1 ;; esac; return 0; }

run() {  # run <heavy|light> <name> <args...>: skip if the previous run of the same lock is still going, or if memory is short
  local kind="$1" name="$2"; shift 2
  [ "$kind" = "light" ] && kind="$name"
  local results=0 bulk=0
  case "$name" in calendars*|results*) results=1 ;; technicals|prism) bulk=1 ;; esac
  # Everything that can wait (the admin-switch read starts Python and opens a database connection) happens inside the background job, so the
  # scheduler's main loop never stalls on it: a stalled loop was a lost time slot.
  ( flock -n 9 || { skipped "$name" "skipped: the previous run was still going"; exit 0; }
    case "$name" in quotes|alerts-live|alerts-daily|screens|digest|drain) ;;
      *) # The light results jobs (calendars, results, results-light) ignore the admin "Heavy data loads" switch: a results date must reach the page
         # whatever that switch says (it was found OFF on 31 Oct, which silently stopped every results job). /api/results/status shows loadsPaused.
         if [ "$results" != 1 ]; then
           loads_paused && { skipped "$name" "skipped: heavy data loads are paused by the admin switch"; exit 0; }
         fi ;;
    esac
    [ "$results" = 1 ] || renice -n 15 -p $BASHPID >/dev/null 2>&1   # bulk work yields CPU to visitors and to reports being prepared for them; the results jobs keep normal priority
    free="$(free_mb)"; need="$MIN_FREE_MB"; [ "$results" = 1 ] && need="$RESULTS_MIN_FREE_MB"
    [ "$free" -lt "$need" ] && { skipped "$name" "skipped: only ${free} MB of memory free"; exit 0; }
    if [ "$bulk" = 1 ]; then flock -w "$BULK_WAIT_S" 6 || { skipped "$name" "skipped: another bulk job held the bulk lock for $((BULK_WAIT_S / 60)) minutes"; exit 0; }; fi
    log "start $name"
    $PY -m finlit.wake ran "$name" >/dev/null 2>&1 &   # the job list at /api/results/status
    # JOB_TIMEOUT_MIN (set by a window for the one job that can run for hours) stops the job politely; every load is resumable
    local cap=(); [ -n "${JOB_TIMEOUT_MIN:-}" ] && cap=(timeout "${JOB_TIMEOUT_MIN}m")
    ${cap[@]+"${cap[@]}"} $PY -m finlit.worker "$@" >> "/tmp/job-$name.log" 2>&1; log "done $name rc=$?" ) 9>"/tmp/finlit-$kind.lock" 6>"$BULK_LOCK" &
  [ "${SYNC:-0}" = 1 ] && wait $!   # inside a DB window the jobs take turns instead of running side by side
  return 0
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
  loads_paused && { log "skip $name (heavy data loads are paused by the admin switch)"; return 0; }
  [ "${FUND_LOADS_ENABLED:-0}" = 1 ] || { log "skip $name (ETF and fund loads are paused: set FUND_LOADS_ENABLED=1 to turn them on)"; return 0; }
  ( flock -w 10800 9 || { log "skip $name (fund jobs busy for 3 hours)"; exit 0; }
    wait_memory "$name" || exit 0
    if [ "$name" = score-mf ]; then flock -w "$BULK_WAIT_S" 6 || { skipped "$name" "skipped: another bulk job held the bulk lock for $((BULK_WAIT_S / 60)) minutes"; exit 0; }; fi
    log "start $name"; $PY -m finlit.wake ran "$name" >/dev/null 2>&1 &
    MALLOC_ARENA_MAX=2 nice -n 15 $PY -m finlit.worker "$@" >> "/tmp/job-$name.log" 2>&1; log "done $name rc=$?" ) 9>"$FUNDS_LOCK" 6>"$BULK_LOCK" &
  [ "${SYNC:-0}" = 1 ] && wait $!
  return 0
}

# Waits (up to 10 minutes) until the web server answers, so the loads below never compete with it while it starts.
wait_web() {
  for _ in $(seq 1 120); do
    $PY -c "import sys,urllib.request; urllib.request.urlopen('http://127.0.0.1:${PORT:-8000}/api/ping', timeout=3)" >/dev/null 2>&1 && return 0
    sleep 5
  done
  return 1
}

# One step of the ETF / mutual fund load: run it, log ONE line with its result, and report failure so the next step is not started.
fund_step() {  # fund_step <label> <worker args...>: takes its turn on the fund jobs' lock, like the nightly runs
  local label="$1"; shift
  loads_paused && { log "$label skipped: heavy data loads are paused by the admin switch"; return 1; }
  [ "${FUND_LOADS_ENABLED:-0}" = 1 ] || { log "$label skipped: ETF and fund loads are paused (FUND_LOADS_ENABLED is not 1)"; return 0; }
  local out rc
  exec 8>"$FUNDS_LOCK"; flock -w 10800 8 || { log "$label skipped: fund jobs busy for 3 hours"; exec 8>&-; return 1; }
  if ! wait_memory "$label"; then exec 8>&-; return 1; fi
  out="$(MALLOC_ARENA_MAX=2 nice -n 15 $PY -m finlit.worker "$@" 2>&1)"; rc=$?
  exec 8>&-
  log "$label rc=$rc $(printf '%s' "$out" | tail -n 1 | cut -c1-300)"
  return $rc
}

# First start: universe, the biggest companies first, then as many as INGEST_LIMIT allows. Resumable.
(
  flock 9
  [ "${BOOT_LOAD_ENABLED:-1}" = 1 ] || { log "boot-load skipped: BOOT_LOAD_ENABLED is not 1 (the big company, ETF and fund loads on start are switched off)"; exit 0; }
  # A restart or deploy must not start the whole load again when it finished less than 20 hours ago: every step would wake the database for hours (the DB windows run the same jobs nightly).
  $PY -m finlit.wake flag-get bootload >/dev/null 2>&1 && { log "boot-load skipped: it finished in the last 20 hours (the nightly DB windows keep the data fresh)"; exit 0; }
  loads_paused && { log "boot-load skipped: heavy data loads are paused by the admin switch"; exit 0; }
  renice -n 15 -p $BASHPID >/dev/null 2>&1   # low CPU priority for the bulk loads; the reports visitors wait for (drain-queue) stay at normal priority
  log "start boot-load"
  sleep "${BOOT_LOAD_DELAY_S:-240}"   # let the web server finish starting and fill its caches first; the loads below compete with it for the 512 MB
  loads_paused && { log "boot-load skipped: heavy data loads were paused during the start-up wait"; exit 0; }
  # Order: what visitors see first (the company list, prices, index membership, the flagship stocks, ETFs and fund NAVs), then the company reports,
  # then the slow histories (macro, flows, fund history). A restart loses nothing: every step is resumable and skips what is already done.
  $PY -m finlit.worker refresh-results                 # first of all: anyone who reported while the site was down or restarting (the quarter page says "being updated" until this runs)
  $PY -m finlit.worker refresh-results-light           # right after: the smaller companies that reported (their quarterly figures only, one provider call each)
  $PY -m finlit.worker refresh-flows --only nse                    # the exchange's own FII/DII figures for the latest session (one request), even when the nightly run is recent
  $PY -m finlit.worker refresh-calendars               # IPO and results calendars: light, and visible at once
  $PY -m finlit.worker refresh-universe
  $PY -m finlit.worker refresh-listing                  # every listed company's price and market cap (skipped if it ran in the last 6 hours)
  $PY -m finlit.worker refresh-indices                  # NIFTY index membership: also decides which companies load first
  $PY -m finlit.worker history-probe                   # a read-only count of yearly statements per source for a few old companies: shown at /api/mf/status (run:history-probe)
  $PY -m finlit.worker rebuild-metrics --only-missing   # screener filters for companies loaded before they existed (database only)
  $PY -m finlit.worker prune                            # stay inside the free database's storage: top INGEST_LIMIT + recently opened
  $PY -m finlit.worker ingest RELIANCE TCS INFY HDFCBANK ICICIBANK SBIN ITC LT BHARTIARTL HINDUNILVR
  $PY -m finlit.worker refresh-short-history          # stored reports with 4 years or fewer are loaded again: the second source adds older years where it agrees with the provider
  # ETFs and the day's fund NAVs (the long fund history comes last), only once the web server is up. None of them runs on a timer, so the database may sleep.
  WEB_UP=0; MF_OK=0
  if wait_web; then
    WEB_UP=1
    fund_step boot-instruments refresh-instruments --max-age-hours 20   # Dhan's public instrument file first: the ETF job reads its ETF list from it
    fund_step boot-etf refresh-etf --max-age-hours 12 --resume   # ETFs first; their result no longer decides whether the mutual fund loads run
    fund_step boot-mf refresh-mf --max-age-hours 12 && MF_OK=1
  else
    log "boot-etf skipped: the web server did not answer within 10 minutes"
  fi
  # Fund facts, the industry report and the five-year NAV history come BEFORE the long company load: every returns column, the SIP figures, fund size and
  # the checklist depend on them, the steps are resumable (one fund house at a time), and a restart during the hours-long company load must not
  # keep them from ever being reached.
  if [ "$WEB_UP" = 1 ] && [ "$MF_OK" = 1 ]; then
    fund_step boot-facts refresh-facts --max-age-hours 20    # fund size, expense ratios, launch dates (AMFI); its result never stops the history load
    fund_step boot-industry refresh-industry --max-age-hours 20   # AMFI's monthly category report (Fund industry trends): resumable, about 90 small files on the first run, then one cheap check
    [ -n "${DHAN_CLIENT_ID:-}" ] && fund_step boot-dhan-check dhan-check      # only when Dhan is set up: proves the credentials; the result is at /api/mf/status (run:dhan-check)
    fund_step boot-mf-history backfill-mf
  fi
  $PY -m finlit.worker ingest-all "${LIMIT_ARGS[@]}" --parallel 1   # one company at a time: two at once pushed the 512 MB instance out of memory and the site answered 502/503
  $PY -m finlit.worker refresh-results                 # anyone who has reported since the last run
  $PY -m finlit.worker refresh-results-light           # and the smaller companies that have
  $PY -m finlit.worker refresh-macro --max-age-hours 20  # India macro data (MoSPI, RBI): the first run loads the full history (about 300 small requests)
  $PY -m finlit.worker refresh-flows --max-age-hours 20  # FII/DII flows (NSDL, NSE archive files): the first run loads the full FPI history, one request per month
  $PY -m finlit.worker score-all                        # a score for every other listed company (score row only, capped per run, resumable)
  $PY -m finlit.worker precompute-prism --max-minutes "${BOOT_PRISM_MAX_MIN:-240}"   # a Prism rating for every company with a full report, so a report opens with it already there (resumable; the nightly window repeats it)
  $PY -m finlit.worker refresh-leadership --if-stale --backfill-from 2022-10-01   # Leader / Laggard labels and their rank history (database only; skipped when this week's run is done)
  # fund holdings and exit loads (fund houses' monthly portfolios, AMFI scheme details): last, so stock loads come first; waits its turn with the other fund jobs; skipped if it ran in the last 20 hours
  flock -w 10800 "$FUNDS_LOCK" env MALLOC_ARENA_MAX=2 $PY -m finlit.worker refresh-portfolios --max-age-hours 20 >> /tmp/job-portfolios.log 2>&1
  flock -w 10800 "$FUNDS_LOCK" env MALLOC_ARENA_MAX=2 $PY -m finlit.worker score-mf --max-age-hours 20 >> /tmp/job-score-mf.log 2>&1
  $PY -m finlit.wake flag-set bootload 72000 >/dev/null 2>&1
  log "done boot-load"
) 9>/tmp/finlit-heavy.lock >> /tmp/job-boot-load.log 2>&1 &

# Stocks opened before they were loaded are prepared in the background. The loop waits on a Redis flag (raised when a visitor opens such a stock), not on
# Postgres, and does not query anything at start; if it ever exits (database refusing connections), it waits 10 seconds before trying again
# (a visitor may be waiting: it used to be 2 minutes).
( while true; do $PY -m finlit.worker drain-queue --loop >> /tmp/job-drain.log 2>&1; sleep 10; done ) &   # always on, at normal priority, outside every lock, memory gate and admin switch: a report a visitor waits for is built at once

# Commodity prices: MCX futures (Dhan) every 10 seconds while MCX trades, international prices (metals.dev / MetalpriceAPI) every minute, into Redis.
# Started only when at least one source is set up; the page says plainly which parts are not connected.
# About 62 MB resident while running; COMMODITIES_WORKER=0 switches it off (the page then says the prices are not connected).
# It reads Postgres at most once a day (duty rates, hours, holidays; kept in Redis) and writes one row set when a day's close arrives.
if [ "${COMMODITIES_WORKER:-1}" != "0" ] && [ -n "${DHAN_CLIENT_ID:-}${METALS_DEV_API_KEY:-}${METALPRICEAPI_KEY:-}" ]; then
  ( while true; do $PY -m finlit.worker refresh-commodities --loop >> /tmp/job-commodities.log 2>&1; sleep 120; done ) &
fi

# ---------------------------------------------------------------------------------------------------------------- Prism ratings, ahead of time
# Every company with a full report gets its FinLit Prism rating calculated in the background, so a report opens with the rating already there.
# This is its OWN loop (its own lock), not the end of the boot chain above: that chain is hours long and a restart starts it again, so a rating
# queued behind it was never reached. Each round works through what is missing (never-rated first, then the biggest), one company at a time,
# gives way to a member who is waiting, stops after three failures in a row and is simply started again by the next round. Resumable: a stored
# rating counts as done. After the companies with a full report it also widens coverage by PRISM_WIDEN_PER_NIGHT (default 30, 0 = off) further companies a night,
# biggest first, paused while members use Prism (docs/prism/COVERAGE_PLAN.md). PRISM_PRECOMPUTE_ENABLED=0 switches it off; the admin switch "Heavy data loads" pauses it like the other loads.
(
  [ "${PRISM_PRECOMPUTE_ENABLED:-1}" = 1 ] || { log "prism-precompute loop off: PRISM_PRECOMPUTE_ENABLED is not 1"; exit 0; }
  flock -n 8 || exit 0
  sleep "${PRISM_PRECOMPUTE_DELAY_S:-180}"
  while true; do
    if loads_paused; then
      log "prism-precompute: waiting (heavy data loads are paused by the admin switch)"
    else
      free="$(free_mb)"
      if [ "$free" -lt "${PRISM_MIN_FREE_MB:-350}" ]; then
        log "prism-precompute: waiting (only ${free} MB free)"
      else
        if flock -n 6; then   # the bulk lock: technicals, score-mf and the nightly Prism run take turns with this loop, never beside it
          n="${PRISM_WORKERS:-2}"   # side by side, each on its own share of the companies; the site backend runs up to PRISM_SLOTS (2) calculations at once
          log "start prism-precompute ($n workers)"
          $PY -m finlit.wake ran prism-loop >/dev/null 2>&1 &
          for k in $(seq 0 $((n - 1))); do
            timeout "${PRISM_ROUND_MAX_MIN:-60}m" nice -n 15 $PY -m finlit.worker precompute-prism --shard "$k/$n" --max-minutes "${PRISM_ROUND_MAX_MIN:-55}" --limit "${PRISM_ROUND_LIMIT:-800}" >> /tmp/job-prism-loop.log 2>&1 &
          done
          wait
          flock -u 6
          log "done prism-precompute"
        else
          log "prism-precompute: waiting (another bulk job holds the bulk lock)"
        fi
      fi
    fi
    sleep "${PRISM_LOOP_SLEEP_S:-300}"
  done
) 8>/tmp/finlit-prism-loop.lock 6>"$BULK_LOCK" >> /tmp/job-prism-loop.log 2>&1 &

# ---------------------------------------------------------------------------------------------------------------- the DB windows
visitor_active() { $PY -m finlit.wake visit-active 15 >/dev/null 2>&1; }   # a visitor was on the site in the last 15 minutes (Redis only)
alerts_active() { $PY -m finlit.wake alerts-active >/dev/null 2>&1; }       # some member alert or watchlist target exists (Redis flag; unknown = yes)
refresh_alerts_flag() { $PY -m finlit.wake refresh-alerts >/dev/null 2>&1 || true; }   # inside a window the database is awake anyway: look once

window() {  # window <name> <chain function>: runs the chain in the background, one chain of the same name at a time
  local name="$1" chain="$2"
  ( flock -n 7 || { log "skip window $name (the previous one is still running)"; exit 0; }
    export SYNC=1; log "window $name: start"; "$chain"; log "window $name: end" ) 7>"/tmp/finlit-window-$name.lock" &
}
dow() { date +%u; }   # 1=Mon .. 7=Sun

chain_night() {   # 01:00: the heavy loads and the audits, one after the other
  local D; D="$(dow)"
  refresh_alerts_flag
  run light drain drain-queue                                      # stocks opened while the loop could not look
  run heavy prune prune
  JOB_TIMEOUT_MIN="${NIGHT_INGEST_MAX_MIN:-150}" run heavy ingest ingest-all --hours 20 "${LIMIT_ARGS[@]}" --parallel 2   # capped at 2.5 hours; resumable
  (( D == 7 )) && run heavy universe refresh-universe
  run heavy score-all score-all
  run light indices refresh-indices
  run light coverage audit-coverage --sample 80 --record
  run light integrity audit-integrity
  (( D == 6 )) && run heavy leadership refresh-leadership         # Saturday: after Friday's close
  (( D == 7 )) && [ "$(date +%d)" -le 7 ] && [ $(( 10#$(date +%m) % 3 )) -eq 1 ] && run heavy leadership-backtest backtest-leadership   # first Sunday of Jan, Apr, Jul, Oct
  run_funds mf-history backfill-mf
  run heavy history backfill-history
  run heavy prism precompute-prism
  run_funds portfolios refresh-portfolios
  run_funds score-mf score-mf                                      # the Mutual Fund Health Score: after the portfolios it reads, same lock and memory rules as the other fund jobs
  run light logos refresh-logos
}
chain_morning() {   # 06:45: before the open
  local D; D="$(dow)"
  refresh_alerts_flag
  run light drain drain-queue
  run light calendars refresh-calendars
  run_funds instruments refresh-instruments
  (( D <= 5 )) && run light screens check-screens
  run light results refresh-results
  run light results-light refresh-results-light
  run light technicals refresh-technicals                          # catches up whatever the evening runs missed (a night when Dhan was late); a no-op when every view is at the newest session
}
chain_close() {   # 15:50 on weekdays: just after the close
  run light listing refresh-listing --force                        # the day's final prices and moves from the exchange feed
  run light results refresh-results
  run light results-light refresh-results-light
  run light calendars-day refresh-calendars
}
chain_technicals() {   # 18:30 on weekdays: the day's candles are final (the exchange closes 15:30; the reports' own rule is 16:00)
  run light technicals refresh-technicals                          # ONLY the short/long-term technical view of every stored Prism report, from fresh Dhan candles (finlit/prism_technical.py): one call per company, resumable, yields to members
}
chain_evening1() {   # 19:10: the evening data (NSE, NSDL, MoSPI, RBI have posted by now)
  local D; D="$(dow)"
  refresh_alerts_flag
  run light flows-nse refresh-flows --only nse
  run_funds industry refresh-industry
  run light macro refresh-macro
  run light flows refresh-flows
  (( D <= 5 )) && run light alerts-daily check-alerts --kind daily
  (( D == 7 )) && run light digest send-digest
  run light listing refresh-listing
  run light results refresh-results
  run light results-light refresh-results-light
}
chain_evening2() {   # 21:10: after AMFI publishes the day's NAVs
  local D; D="$(dow)"
  run_funds mf refresh-mf
  run_funds facts refresh-facts
  run light flows-retry refresh-flows
  if (( D <= 5 )); then run_funds etf refresh-etf; run_funds etf-retry refresh-etf --resume; fi
  run light results refresh-results                                # most companies declare between 15:00 and 23:59 IST: pick them up in the late windows too
  run light results-light refresh-results-light
  (( D <= 5 )) && run light technicals refresh-technicals          # the late retry: companies the 18:30 run could not reach (Dhan late, a busy evening) are picked up; stops at once when none is behind
}
chain_late() {   # 23:30: after AMFI's 11 pm deadline
  local D; D="$(dow)"
  run_funds mf-late refresh-mf
  (( D <= 5 )) && run_funds etf-retry2 refresh-etf --resume
  run light calendars-late refresh-calendars                       # board-meeting dates announced during the day
  run light results refresh-results
  run light results-light refresh-results-light
}

results_gate() { [ "${RESULTS_NEED_VISITOR:-0}" != 1 ] || visitor_active; }   # see the results jobs below

# A time slot fires once a day, at its minute or up to 10 minutes later: a loop round that was late (the box is busy with bulk jobs) used to lose the
# whole slot, because the old test was "the minute is exactly :20". A slot already behind when the scheduler started is not made up (the boot load does that).
declare -A DONE
printf -v START_DAY '%(%F)T' -1; START_MIN=$(( 10#$(date +%H) * 60 + 10#$(date +%M) )); LAST_DAY="$START_DAY"
due() {  # due <name> <hour> <minute> [grace minutes]; uses H and M of the current round
  local today at=$(( $2 * 60 + $3 )) late=$(( H * 60 + M - $2 * 60 - $3 ))
  printf -v today '%(%F)T' -1
  if [ "$today" != "$LAST_DAY" ]; then DONE=(); LAST_DAY="$today"; fi
  [ -n "${DONE[$1]:-}" ] && return 1
  (( late >= 0 && late <= ${4:-10} )) || return 1
  [[ "$today" > "$START_DAY" ]] || (( at >= START_MIN )) || return 1
  DONE[$1]=1; return 0
}
last=""
while true; do
  now="$(date '+%M %H %u')"; [ "$now" = "$last" ] && { sleep 5; continue; }; last="$now"
  $PY -m finlit.wake heartbeat >/dev/null 2>&1 &   # once a minute: shown at /api/results/status as schedulerAliveAt, so the scheduler's own life can be checked from a browser
  read -r M H D <<< "$now"; H=$((10#$H)); M=$((10#$M)); D=$((10#$D))   # D: 1=Mon .. 7=Sun
  weekday=$(( D >= 1 && D <= 5 )); market=$(( weekday && H >= 9 && H <= 15 ))
  QE="${QUOTES_EVERY_MINUTES:-1}"   # minutes between live-price updates while a visitor is on the site

  # The DB windows (see the top of this file)
  due night 1 0 && window night chain_night
  due morning 6 45 && window morning chain_morning
  (( weekday )) && due close 15 50 && window close chain_close
  (( weekday )) && due technicals 18 30 && window technicals chain_technicals
  due evening1 19 10 && window evening1 chain_evening1
  due evening2 21 10 && window evening2 chain_evening2
  due late 23 30 && window late chain_late

  # Outside a window: member price alerts, every 15 minutes in market hours, only when an alert or watchlist target exists (prices are refreshed just before)
  if (( market && M % 15 == 0 )) && alerts_active; then
    ( export SYNC=1; run light quotes refresh-quotes; run light alerts-live check-alerts --kind live ) &
  fi
  # Outside a window: only while a visitor was on the site in the last 15 minutes
  (( market && M % QE == 0 )) && visitor_active && run light quotes refresh-quotes
  # Results jobs: every hour from 08:20 to 23:59 IST, every day including weekends (companies declare on Saturdays too), NO visitor needed: a declaration
  # must not wait for someone to open the site. Each run asks the database for a short list first and does nothing when it is empty. RESULTS_NEED_VISITOR=1
  # restores the old rule (only while a visitor was on the site in the last 15 minutes) for a metered database.
  if (( H >= 8 && H <= 23 )); then
    due "cal-$H" "$H" 5 && results_gate && run light calendars-hourly refresh-calendars                  # new board-meeting dates (two provider calls)
    due "res-$H-a" "$H" 20 && results_gate && run light results refresh-results                          # companies that have just reported are rebuilt within the hour
    due "res-$H-b" "$H" 50 && results_gate && run light results refresh-results
    due "light-$H" "$H" 35 && results_gate && run light results-light refresh-results-light              # their quarter figures, one provider call each
  fi
  sleep 20
done
