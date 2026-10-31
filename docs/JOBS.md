# Background jobs: the job supervisor

Written after the 31 Oct 2026 incident. **Goal: failures are impossible to miss, recover by themselves, and stale data is never shown as fresh.**
No system can promise zero failures (see "What cannot be guaranteed" at the end); this one makes sure the founder is told, the box heals, and the pages say when data is old.

## 1. What went wrong, and what now prevents it

| Incident cause (31 Oct) | What now makes it impossible to repeat |
|---|---|
| The admin switch "Heavy data loads" was OFF for a long time, every job skipped silently | The switch is a **time-boxed pause** (30 min default, 2 h, 12 h; longer needs a confirmation). It ends by itself; an old "off" with no expiry is read as "paused until 30 minutes after it was first seen". Results, calendars, quotes, alerts and report builds ignore it. The status shows who/until when. |
| Skips were only visible in a Redis note | Every non-start has a recorded reason: `job_runs` row (status `skipped`), `job_state.state_reason`, `GET /api/jobs/status`, admin banner. |
| Technical scores were 19 days old with nobody noticing | **Data-freshness invariants** (section 5) look at the newest DATA DATE, not at job success; a stale dataset forces its job to run now and alerts the founder by email and in-app. |
| Three heavy jobs at once on 2 GB | Bulk jobs run strictly **one at a time** (`BULK_CONCURRENCY`, default 1), niced, `oom_score_adj +500`, after a memory/CPU gate. |
| Exact-minute slots lost the whole slot when a round was late | Nothing is a slot any more: each minute the supervisor asks "is it **due**?" (SLA breached, window open and not yet done, interval passed). A late supervisor finds the job still due. |
| A failed / OOM-killed / hung job waited for the next calendar slot | Retry after **30 min, then 60, then 120** (reset by a success); a hung job is killed by the watchdog and retried the same way; after 5 failures in a row the job is "held", the founder is alerted, and it is **still retried every 2 hours**. |
| Manual `docker compose exec` workers lacked an env var only start.sh exported | Fixed in `config.py` earlier; the supervisor starts jobs with the container's own environment. |

## 2. Architecture

```
start.sh (deploy/render-start.sh) -> nohup deploy/scheduler.sh
   scheduler.sh keeps alive (restart with a growing delay, max 5 min):
     1. python -m finlit.worker supervise      <- ALL scheduling
     2. drain-queue --loop                      <- on-demand lane (a visitor opened an unloaded stock), outside every gate
     3. refresh-commodities --loop              <- commodity prices (only when a source is configured)
```

`backend/finlit/jobs/`

| File | Role |
|---|---|
| `registry.py` | **Declarative list of every job** (name, command, class, priority, max runtime, memory weight, group, windows, interval, SLA, prerequisites, retry policy, env gate). Also `JobsConfig` (env knobs). |
| `schedule.py` | IST windows, market hours, expected-session rule (same as `prism_candles.expected_session`). |
| `due.py` | Pure functions: `evaluate(job, state, ctx) -> due / waiting / idle / held / disabled`, `sla_status`, `next_due_at`, retry delays. No I/O. |
| `supervisor.py` | The loop: decide, gate on memory/CPU, start, watch, retry, force on stale data, alert. |
| `runner.py` | Starts job processes (own process group, niced, `oom_score_adj`, log file, heartbeat file) and the fake used in tests. |
| `resources.py` | cgroup v2 / v1 / `/proc/meminfo` free memory, load average, disk percent. |
| `state.py` | `job_runs` (history) and `job_state` (current) in Postgres (migration `077_jobs.sql`); in-memory twin for tests. |
| `pause.py` | The time-boxed pause (`mf_meta` key `switch:loads`), legacy migration, expiry. |
| `freshness.py` | Data-freshness invariants per dataset (section 5). |
| `canary.py` | Daily value self-check against fresh provider calls (section 6). |
| `alerts.py` | In-app notification + email to every admin, once per 6 h per problem; the web-process heartbeat watcher. |
| `status.py` | `GET /api/jobs/status`. |
| `probes.py`, `signals.py`, `cli.py` | cheap "is there work?" questions, Redis facts/lock/heartbeat, the `supervise` command. |

**Decision: the quote and alert loops are registry jobs, not bash.** The old per-minute light loops in bash had no memory gate, no history, no status and no retry. As registry jobs (`quotes`, `alerts-live`, `listing`) they get all of those. Nothing time-driven is left in `scheduler.sh`.

### Job classes and concurrency

* **bulk** (`technicals`, `ingest`, `score`, `prism`, `portfolios`, `score-mf`, `backfill-*`, `leadership`, `prune` ...): at most `BULK_CONCURRENCY` (default **1**) at a time, in priority order, first come first served among equals, `nice 15`, `oom_score_adj +500`, `MALLOC_ARENA_MAX=2`.
* **light** (results, calendars, quotes, listing, alerts, the fund data jobs ...): up to `LIGHT_CONCURRENCY` (default **2**) beside the bulk job. Jobs in one `group` (the fund jobs: `funds`) never run together.
* **ondemand** (`drain-queue`, `commodities`): their own always-on processes; listed in the status as "kept alive by scheduler.sh", never started by the supervisor, never gated.
* **Prerequisites**: a job waits while a prerequisite is running or due (score-mf after portfolios; score and prism after ingest). A prerequisite in backoff or held does **not** block for ever.
* **Memory gate**: a job starts only if `free MB >= weight` (bulk: weight + `JOBS_RESERVE_MB`, default 100, kept for the website), counting what was started in the same tick. Free memory = container limit minus usage plus droppable page cache. **A job that does not fit WAITS** ("waiting for memory: 300 MB free, needs about 550 MB"), is recorded, and is retried every tick: never skipped silently. A second bulk job also waits while the load average per core is above `JOBS_MAX_LOAD_PER_CPU` (3).
* After a (re)start bulk and fund jobs wait `BOOT_LOAD_DELAY_S` (240) for the web server to settle. Results jobs do not wait.

## 3. When is a job due?

Per job, each tick (60 s; and at once when a job ends):

1. **disabled** by an env gate: state `disabled`, reason shown, flagged `disabledByConfig`, **never counted as overdue**. (`FUND_LOADS_ENABLED` must be `1` for the fund jobs; `PRISM_PRECOMPUTE_ENABLED=0` stops Prism; `dhan-check` needs `DHAN_CLIENT_ID`.)
2. **backoff**: after a failure the job is not due before `retry_at` (30 / 60 / 120 min). Retries ignore windows and visitors.
3. Otherwise it is due when any of these holds:
   * freshness forced it (a dataset it owns is stale);
   * a retry is owed;
   * it never succeeded (first start / boot catch-up; not for jobs that send mail; `BOOT_LOAD_ENABLED=0` stops this for first-start loads);
   * **a quiet window is open** and its last success is older than the window's `min_age_h`;
   * its **interval** has passed (inside its active hours / market hours; quotes follow visitors, `RESULTS_NEED_VISITOR=1` restores "only while a visitor is on the site" for the results jobs);
   * its **daily time** has passed without a success that day (`listing` 15:50, `alerts-daily` 19:10 ...);
   * a **probe** says there is work (technicals: more than 2% of reports behind; prism: unrated companies);
   * its **SLA is breached**: outside a window it runs if no visitor was active in the last 15 minutes, or if the breach exceeds 2 x the SLA (**never starved**). With visitors present and less than 2 x late it waits with the reason "waiting for a quiet moment".
4. The **admin pause** turns a due job into `waiting` ("paused by the admin until 14:35 IST; resumes automatically") for jobs that honour it (all bulk and fund jobs).

### Windows (IST, no daylight saving)

| Window | Hours | Used for |
|---|---|---|
| MORNING | 05:00 to 06:45 | the full catch-up chain: whatever the night missed, plus results, calendars, listing before the open (fewest visitors) |
| AFTER_CLOSE | 18:30 to 21:30 | technicals, flows, macro, industry, AMFI NAV (from 21:10), facts, ETF, listing |
| NIGHT | 23:30 to 03:30 (wraps midnight) | the heavy loads: ingest-all, score-all, prune, funds, backfills, indices, audits |

A window instance is the specific open span, so NIGHT 23:30 Friday to 03:30 Saturday is one instance. Weekly jobs use a day rule evaluated on the IST date (leadership: Saturday, so it runs Saturday 00:00 to 03:30).

## 4. The registry (every job, its SLA, window, class)

SLA kinds: `hours` a success within N hours; `active` N hours counted only from 08:00 to 23:59 IST (no false alarms at night); `session` a success after each trading day's data is final (18:30), overdue 12 h later; `none`. **Overdue = 1.5 x SLA** (that is when the founder is alerted). "w" = windows with minimum age; "int" = interval.

| Job (command) | Class | Pri | SLA | Schedule |
|---|---|---|---|---|
| results (`refresh-results`) | light | 1 | 1.5 h active | int 25 min 08-23; MORNING; ignores pause |
| results-light | light | 2 | 2 h active | int 55 min 08-23; MORNING; ignores pause |
| calendars (`refresh-calendars`) | light | 3 | 1 h active | int 40 min 08-23; MORNING; ignores pause |
| quotes (`refresh-quotes`) | light | 4 | none | every minute with a visitor, every 15 min if only alerts, market hours |
| alerts-live (`check-alerts --kind live`) | light | 5 | none | 15 min market hours, after quotes, only if alerts exist |
| listing (`refresh-listing --force`) | light | 6 | 6 h | 30 min market hours; 15:50; AFTER_CLOSE; MORNING |
| canary | light | 7 | 30 h | MORNING; AFTER_CLOSE from 19:00 |
| alerts-flag / alerts-daily / screens / digest | light | 8-9 | none / 80 h / 80 h / 8 d | each window / weekdays 19:10 / MORNING weekdays / Sunday 19:10 |
| prune | bulk | 5 | 30 h | NIGHT |
| **technicals** (`refresh-technicals`) | bulk | 10 | session, 12 h | AFTER_CLOSE and MORNING until the session is processed; probe re-runs every 30 min |
| ingest-flagship / **ingest** (`ingest-all`) | bulk | 15 / 20 | 26 h | NIGHT (18 h), MORNING (14 h); 90 min per run, resumable |
| **score** (`score-all`) | bulk | 30 | 26 h | NIGHT, MORNING; after ingest |
| **prism** (`precompute-prism`, 2 shards) | bulk | 40 | 26 h | probe every 10 min + NIGHT + MORNING; after ingest and score |
| leadership | bulk | 45 | 8 d | Saturday NIGHT |
| portfolios, score-mf, backfill-mf (funds, `FUND_LOADS_ENABLED=1`) | bulk | 50, 55, 60 | 26 h, 26 h, 8 d | NIGHT, MORNING; score-mf after portfolios |
| backfill-history | bulk | 65 | 8 d | NIGHT, MORNING |
| backtest-leadership | bulk | 70 | 100 d | first Sunday of Jan/Apr/Jul/Oct, NIGHT |
| rebuild-metrics, short-history, history-probe, dhan-check, universe (Sunday) | bulk/light | 71-85 | 8-17 d | weekly NIGHT |
| indices, coverage, integrity, logos | light | 60-80 | 30 h (logos 60 h) | NIGHT, MORNING |
| macro, flows-nse, flows | light | 19-21 | 30 h | AFTER_CLOSE from 19:10; flows twice; MORNING |
| instruments, mf, facts, industry, etf (funds) | light | 22-26 | 30 h (mf 26, etf 80) | MORNING / AFTER_CLOSE from 21:10 / NIGHT; etf weekdays |
| drain-queue, commodities | ondemand | - | - | always on (scheduler.sh) |

`backend/tests/test_jobs_registry.py` asserts every command the old bash scheduler ran is registered, and that each of its old time slots is covered by the same job at or before that time.

## 5. Data-freshness invariants (a job can "succeed" and still leave stale data)

`jobs/freshness.py` runs inside the supervisor every 10 minutes and reads the **newest data date** of each dataset, compared with what the IST clock, the trading calendar and the declaration calendar say must exist now. Result in `GET /api/jobs/status` under `data` (and `dataFresh`). Each dataset: `expected`, `actual`, `lag`, `status` fresh|late|stale|unknown, owning `jobs`.

| Dataset (key) | Expected | late / stale | Owner |
|---|---|---|---|
| Stock quotes, ticker | market open: newest quote under 60 min old; after hours: taken after the expected session's close | 180 min / 14 h after the close is final | listing, quotes |
| Daily price history | reference large caps have the expected session's bar | 1 h after 18:30 + grace / +14 h | technicals, ingest |
| Index levels | fetched on demand; if market open and a visitor is looking: under 10 min | 30 min | (on demand) |
| Technical views | at most 2% of reports behind the expected session | after 19:30 / >25% behind and 10 h | technicals |
| Prism ratings, FinLit scores | newest row under 30 h | 60 h | prism, score |
| Quarterly results | no company whose declaration date passed still lacks figures: waiting yesterday = late, two or more days = stale (declaration is known by DATE only; target is 6 h, flagged at 24 h) | | results, results-light |
| Results calendar | refreshed under 3 h ago and upcoming dates exist | 12 h | calendars |
| IPO calendar, news, leadership | under 30 h / 3 days / 9 days | 96 h / 6 d / 14 d | calendars, leadership |
| FII/DII flows, ETF prices | the expected session | +3 h / +16 h | flows, etf |
| Mutual fund NAV | the last business day after 23:30 IST | one business day behind (could be an AMFI holiday) / two | mf |
| Fund scores | run under 40 h ago | 80 h | score-mf |

Holidays are not guessed: the expected session is `expected_session()` (latest weekday whose session is complete, today from 16:00 IST), lowered to the newest session the technicals job actually found when that is older (a market holiday).

**Stale = action**: the owning job is forced due now (bypassing windows and visitors, but not the admin pause or backoff), at most **2 times** per staleness episode and 10 minutes apart; if the data is still stale after the second run the founder is alerted ("FinLit data is stale: ..."). The counter clears when the data turns fresh.

**System checks**: disk usage of `/` (alert at 85%; the `prune` job runs nightly at the top of the bulk order), database size, refused provider keys (below).

## 6. Value self-checks (wrong data, not only old data)

* Existing guards stay: Dhan index level more than 10% from the one held is refused; a Dhan quote whose previous close is more than 25% from the price held falls back to FinEdge; the technical view refuses candles with gaps or a close outside the high/low.
* **Canary** (`jobs/canary.py`, command `canary`, twice a day): re-fetches RELIANCE, TCS, HDFCBANK, INFY, one small cap (market cap 200 to 2,000 Cr, picked by a daily hash) and the most recent listing, and compares our stored **price** (0.5% closed, 3% open), **market cap** (5% / 8%), **last daily close** (0.5%, only when our newest bar is the latest session's) and **latest quarter revenue and net profit** (0.5%) with the fresh provider answer. Any difference is listed in `GET /api/jobs/status` `canary.mismatches` with both values, `healthy` becomes false, and the founder is alerted. Tolerances are returned with the result. If the provider cannot be reached, `ok` is `null` (not "fine").

## 7. Alerts without SSH

The founder is emailed (`ADMIN_EMAIL` account, every active admin) and gets an in-app notification (link `/console`), at most **once per 6 hours per problem** (Redis key `jobs:alert:<problem>`; in-process fallback if Redis is down), when:

* a job is overdue by more than 1.5 x its SLA (`overdue:<job>`);
* a job fails 3 times in a row (`failing:<job>`; after 5 it is "held" and retried every 2 h);
* a dataset is stale after two forced runs (`stale:<dataset>`);
* the supervisor heartbeat is older than 5 minutes: **checked by the web process** (a task in the API app), because a dead supervisor cannot report itself (`supervisor`);
* a provider key is refused (HTTP 401/403 from Dhan or FinEdge): "The Dhan key is not accepted: update it in /opt/finlit/.env.aws" (`cred:dhan`, `cred:finedge`);
* disk 85% full (`disk`); the canary found a mismatch (`canary`).

**Admin Console, Data health tab**: a banner (`JobsBanner`) lists everything above in plain words; green when healthy. **Public results page** (`/results`, `/results/quarter`): the neutral line "Results refresh is delayed; we are retrying." when a results job is late (`resultsDelayed`).

### Reading `GET /api/jobs/status` (public, read-only, no secrets, no addresses)

```
healthy        true only if: supervisor alive (heartbeat under 5 min), database readable, nothing overdue, no refused key, canary not failing, no stale dataset
healthNote     the reasons when false
overdue        jobs past 1.5 x SLA            failing  jobs with 3+ failures in a row
supervisor     { alive, heartbeatAgeSeconds, running: [...], dbOk, startedAt }
pause          { paused, untilIST, resumesAutomatically, setBy: "admin", legacy }
jobs[]         per job: state idle|due|waiting|running|held|disabled, reason, lastSuccessAt, ageHours, slaHours, slaKind,
               late, overdue, nextDueAt, consecutiveFailures, retryAt, held, disabledByConfig, disabledReason
disabledByConfig  jobs switched off by an env variable, with the fix (never "overdue")
data / dataFresh  the freshness table of section 5       canary  the section 6 result
resultsDelayed true when a results job is late            system  diskPercent, databaseMb
```

By hand: `docker compose exec app python -m finlit.worker jobs-status` (same JSON), `... supervise --dry-run` (what is due and why, starts nothing), `... supervise --once` (starts what is due now, waits for it, prints the table; refused while the daemon holds the lock).

## 8. Retry rules

| Event | Result |
|---|---|
| exit code in `ok_exit` (0; audits also accept 1) | success, failures reset to 0 |
| other exit code, killed by a signal (OOM kill = SIGKILL), could not start | `failed` / `killed`; failures + 1; retry in 30, 60, then 120 minutes |
| ran past `max_runtime` | process group stopped (TERM, KILL after 20 s), `timeout`; retry in 30 min (counts as a failure) |
| a **resumable** job reaching its time cap | `timeout`, **not** a failure; continues in 2 minutes (other bulk jobs get their turn first) |
| no output and no heartbeat for `stall_min` (25 min default) | treated as hung: stopped, `timeout`, retry in 30 min |
| 5 failures in a row | `held`: alert; still retried every 2 hours |
| supervisor restarted mid-run | stale `running` rows become `killed`, leftover processes are stopped, retry in 1 minute (no failure counted) |

Jobs print progress (log file under `/tmp/job-<name>.log`); the worker also touches `FINLIT_JOB_HEARTBEAT` every 20 s while its event loop is alive. Liveness = newest of log write and heartbeat.

## 9. Admin pause

Header lock icon > System > "Heavy data loads" switch. Switching OFF pauses for the chosen length (30 min default, 2 h, 12 h); the line "Paused until 14:35 IST, resumes automatically" shows the end. API: `POST /api/admin/system/loads {"enabled": false, "minutes": 120}`; more than 12 hours needs `"confirmLong": true` (422 `confirm_long_pause` otherwise). Switching ON resumes at once. At the expiry the supervisor (and any status read) treats the loads as running and writes `resumedAuto`. A row from before this change ("off", no expiry) is read as paused until 30 minutes after first seen, and logged.

## 10. Resource knobs (environment, all optional)

| Variable | Default | Meaning |
|---|---|---|
| `BULK_CONCURRENCY` | 1 | bulk jobs at once (2 only on a 4 GB box) |
| `LIGHT_CONCURRENCY` | 2 | light jobs beside the bulk job |
| `JOBS_TICK_S` / `JOBS_POLL_S` | 60 / 5 | decision period / process check period |
| `JOBS_RESERVE_MB` | 100 | memory left for the website when starting a bulk job |
| `JOBS_MAX_LOAD_PER_CPU` | 3.0 | a second job waits above this 1-minute load per core |
| `BOOT_LOAD_ENABLED` | 1 | 0: first-start loads do not start just because they never ran (windows and 2 x SLA still apply) |
| `BOOT_LOAD_DELAY_S` | 240 | bulk jobs wait this long after a start |
| `FUND_LOADS_ENABLED` | 0 | must be 1 for the fund/ETF jobs (else shown as disabled by configuration) |
| `PRISM_PRECOMPUTE_ENABLED`, `PRISM_WORKERS` (2) | 1 | Prism job on/off, shards per run |
| `INGEST_LIMIT`, `INGEST_PARALLEL` (2), `NIGHT_INGEST_MAX_MIN` (90) | | ingest-all size, parallelism, cap per run |
| `RESULTS_NEED_VISITOR` | 0 | 1: results jobs run only while a visitor is on the site |
| `QUOTES_EVERY_MINUTES` | 1 | quotes period while a visitor is on the site |
| `JOBS_WATCH` | 1 | 0 switches off the web process's supervisor watcher |

### Memory plan and swap (2 GB t3.small)

* **Swap**: `deploy/aws/bootstrap.sh` creates a 2 GB swapfile if none exists (idempotent; swappiness 10, vfs_cache_pressure 50). On the existing server, one line (safe to repeat, does nothing if swap exists): `swapon --show | grep -q . || (sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile && echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab && echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-finlit.conf && sudo sysctl --system)`. Check with `free -m`.
* **Limits** (`docker-compose.aws.yml`): app 1200 MB, db 640 MB, redis 320 MB, caddy 128, backup 128 (runs 02:00 only). They are ceilings, not reservations (sum 2.4 GB against 2 GB RAM + 2 GB swap); do not raise the app limit on this box. A bulk job's memory weight (250 to 450 MB) is checked against what is actually free inside the app's limit.
* **OOM order**: job processes get `oom_score_adj +500` (set in the child before exec), so when memory runs out the kernel kills a job first and the API survives; db, redis and caddy get `-300` in compose. The killed job is retried within 30 minutes.
* **Optional upgrade (founder decision, costs money)**: a t3.medium (4 GB, about double the t3.small price) would allow `BULK_CONCURRENCY=2` (e.g. technicals beside ingest) and an app limit around 2.4 GB. Not needed for correctness; the sequential design is sized for 2 GB.

## 11. How to add a job

1. Make sure `python -m finlit.worker <command>` exists, exits 0 on success, prints progress lines, and is resumable if long.
2. Add a `Job(...)` in `registry.py` with class, priority, `max_runtime_min`, `weight_mb`, a schedule (`windows` / `interval_min` / `daily_at` / `probe`), an `Sla`, `prerequisites`, `resumable`, `gate` (if an env switch controls it), and `owns=(dataset keys)` if it keeps a freshness dataset current.
3. If it owns a dataset, add or adjust the check in `freshness.py`; every dataset's `jobs` must name registered jobs (tested).
4. Add the due-ness case to `tests/test_jobs_registry.py` (schedule coverage) and run `pytest tests/test_jobs_*.py`.
5. Add a row to the table in section 4.

## 12. Failure-mode table

| Failure | Detected by | Recovers by itself | The alert says | The founder does |
|---|---|---|---|---|
| Provider down or erroring (FinEdge/Dhan/NSE/AMFI) | job exit != 0 or no new data date | retry 30/60/120 min (held after 5, still every 2 h) | "job failing: X" after 3 failures; "data is stale" if the date stays old | Nothing; if it persists check the provider's status page. Pages keep showing the last good data with its "as of" date. |
| **Dhan token expired / key refused (401/403)** | `report_refused` flag from `dhan.py` | Dhan auto-renews when PIN and TOTP secret are set; otherwise no | "The Dhan key is not accepted: update it in /opt/finlit/.env.aws" | Put a new `DHAN_ACCESS_TOKEN` (or check PIN/TOTP), `docker compose up -d app` |
| **FinEdge key invalid/expired** | `report_refused` from `finedge.py` | no | "The FinEdge key is not accepted ..." | Update `FINEDGE_API_KEY` in `/opt/finlit/.env.aws`, restart the app |
| Rate limit (429) | clients retry with back-off; job failure if persistent | retried | failing/stale as above | Nothing; lower `PRISM_WORKERS`/`INGEST_PARALLEL` if frequent |
| Database storage full | job errors; `databaseMb` in status | no | job failing (disk errors) | Free space / grow the volume; run `prune` |
| **Disk full (box was 62%)** | `system.diskPercent` >= 85% | the nightly `prune` (first in the bulk order) | "FinLit server disk is almost full" | `docker system prune -f`, clear old backups/logs, grow the EBS volume |
| Memory pressure | memory gate; OOM kill = SIGKILL | job waits (never skipped) or is killed first (+500) and retried within 30 min | none unless it repeats (then failing/overdue) | If frequent: keep `BULK_CONCURRENCY=1`; consider the 4 GB instance |
| Container restart mid-job | stale `running` rows | supervisor start marks them killed, stops leftovers, retries in 1 min | none | Nothing |
| Redis flushed/restarted | lock/heartbeat/visitor keys vanish | keys rewritten next tick; alert rate-limit falls back to in-process | none | Nothing |
| Clock / timezone error | all rules are IST via `zoneinfo` (container TZ=Asia/Kolkata); tests use a fake clock | n/a | datasets late/stale if the host clock is wrong | `timedatectl`; fix NTP |
| Supervisor crash | heartbeat age > 5 min (web-process watcher) | scheduler.sh restarts it (5 s, doubling to 5 min); Redis lock prevents two | "FinLit background jobs are not running" | `docker compose restart app` if it persists; read `/tmp/job-supervisor.log` |
| Hung job | no output/heartbeat for 25 min or past max runtime | killed, retried in 30 min | failing/overdue if it repeats | Read `/tmp/job-<name>.log` |
| **Schedule misconfiguration (FUND_LOADS_ENABLED=0)** | gate in the registry | n/a | status `disabledByConfig` + banner note (not "overdue") | Set `FUND_LOADS_ENABLED=1` in `.env.aws` |
| Admin pause left on | expiry | resumes at the end | banner note while paused | Nothing |
| Postgres down | tick fails, heartbeat says `dbOk: false` | next tick retries; running jobs keep being watched | supervisor/health false | Check the db container |
| Provider sends wrong numbers | canary (section 6) | no (it cannot know which side is right) | "canary found data that differs" | Compare with the provider's own site |

## 13. Runbook: what to do when ...

* **Open `/api/jobs/status`.** `healthy: true` and `dataFresh: true` = nothing to do.
* *`supervisor.alive` false*: `docker compose logs --tail 100 app | grep supervisor`; `docker compose restart app`.
* *A job is `overdue`*: read its `state` and `reason`. "waiting for memory" for hours: something else is using the box (check `free -m`, `docker stats`). "paused": see `pause`. "disabled": the env fix is in the reason.
* *A dataset is `stale`*: the owner job was forced twice already. Read the job's last result (`jobs[].lastStatus`, `/tmp/job-<name>.log`), then the provider status.
* *Run a job now*: `docker compose exec app python -m finlit.worker <command>` (the supervisor does not mind; it will see the new success).
* *Heavy loads need to be stopped for a while*: System > switch off; it resumes by itself.
* *After a deploy*: nothing; the supervisor starts with the container, reconciles, and catches up whatever is due (in priority order, one bulk job at a time).

## 14. What cannot be guaranteed

* **Third-party outages** (FinEdge, Dhan, NSE, NSDL, AMFI): when a provider is down the data cannot be fresh. The system retries, tells the founder, and the pages show the date of the data they hold.
* **Wrong data from the provider itself**: the canary and plausibility guards catch differences between our copy and the provider's fresh answer and absurd jumps, not an error the provider repeats consistently.
* **Declaration time**: results are known by date, so "figures within 6 h of the declaration" is enforced as "same day / next day", not to the hour.
* **Holidays** are inferred (the newest session actually found), not read from an exchange calendar.
* Everything here was tested with a fake clock and fake processes; the real process runner, cgroup memory reading, `oom_score_adj` and email delivery can only be proven on the server (first-deploy checklist in `deploy/aws/README.md`).
