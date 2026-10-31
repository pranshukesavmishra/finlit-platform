# Results refresh: how the latest results reach the site

## The pipeline
1. `refresh-calendars` asks the provider (FinEdge `/results-calendar`, 100 days back to 120 ahead) for board-meeting dates and stores them as `result` rows in `feed_items` (source "FinEdge results calendar"). Exchange filings that say "financial results" are stored as `result` rows too, whenever a company is loaded.
2. A company whose results date has passed (or that has a results filing) in the last 4 days is "declared". The Results pages list it at once, with "figures loading" until its numbers are in.
3. `refresh-results` rebuilds the full report of declared companies the site holds in full (provider calls for the whole bundle). `refresh-results-light` fetches only the quarterly profit and loss for the other declared companies and stores it in `quarter_light`.
4. Retry rule: a company the provider has no figures for is asked again at every run for two days after its declaration, then every 3 hours (day 3), then every 5 hours (day 4), then dropped. A run stops after 10 provider failures in a row.

## Schedule (IST): the job supervisor, `docs/JOBS.md`
> Since the 31 Oct incident the bash scheduler's time slots are gone. `deploy/scheduler.sh` only keeps the **job supervisor** (`python -m finlit.worker supervise`) alive; the supervisor decides what is due from each job's SLA, so a late round or a restart can no longer lose a slot.

- `refresh-calendars` (SLA 1 h), `refresh-results` (SLA 1.5 h) and `refresh-results-light` (SLA 2 h) are **light jobs that ignore the admin pause and never wait for a visitor**: every 40 / 25 / 55 minutes from 08:00 to 23:59 IST every day (companies declare on Saturdays too), and once in the MORNING window (05:00 to 06:45) before the active hours begin. `RESULTS_NEED_VISITOR=1` restores "only while a visitor is on the site".
- A job that cannot start is **never skipped silently**: its state is `waiting` with the reason (memory, a light slot, the pause), recorded in `job_runs`, shown at `GET /api/jobs/status` (`jobs[].reason`) and, for the results jobs, still mirrored to `/api/results/status` as `lastSkipped`.
- If a results job is late (past its SLA) the public results pages show "Results refresh is delayed; we are retrying." (`resultsDelayed` in `/api/jobs/status`); past 1.5 x the SLA the admin is emailed.
- Freshness is checked on the DATA, not only on the job: companies whose declaration date has passed but still have no figures are counted (`data.datasets` key `results`): yesterday's = late, two days or older = stale, which forces the results jobs to run again and alerts after two attempts.
- Logs: `/tmp/job-supervisor.log`, `/tmp/job-<name>.log` inside the app container.

## Is the scheduler itself alive? (added after the 31 Oct report)
- `/api/results/status` now has `schedulerAlive`, `schedulerAliveAt` (IST), `schedulerAgeSeconds` and `jobsLastHour` (every job `scheduler.sh` started in the last hour). The job supervisor writes its heartbeat every 5 seconds (the same `scheduler:alive` key). `schedulerAlive: false` means the scheduler is not running (or Redis cannot be read): restart the app container.
- `loadsPaused` shows the admin switch "Heavy data loads", which is now a time-boxed pause that ends by itself (`/api/jobs/status` `pause`). The results jobs (calendars, results, results-light) and the on-demand report builder IGNORE it; it pauses only the bulk loads (technicals, Prism, funds, nightly ingest). On 31 Oct it was found OFF, which had stopped every results job before they were exempted. `/api/technicals/status` shows `loadsPaused` too.
- A time slot now fires once a day at its minute or up to 10 minutes late (the old test was "the minute is exactly :20", so a loop round delayed by a busy box lost the whole slot).
- A worker command that skips Prism work names what is missing: `site_api_url_not_set` or `cms_jwt_secret_too_short`. `SITE_API_URL` now defaults to the local site backend exactly as `render-start.sh` decides, so `docker compose exec ... worker refresh-technicals` behaves like the scheduler.
- Fund jobs (ETF, mutual funds, score-mf, portfolios) run only when `FUND_LOADS_ENABLED=1` in `/opt/finlit/.env.aws` (the example file ships `0`). After editing: `cd /opt/finlit && docker compose --env-file .env.aws -f src/finlit-platform/deploy/aws/docker-compose.aws.yml up -d app`.

## Check it from a browser (no SSH)
- `https://<your site>/api/results/status` shows `todayIST`, `newestResultInDb`, `newestFilingInDb`, `upcomingCount`, `lastRun.calendars|results|resultsLight` (`at` is UTC, `status`, `counts`, `newestResultDate`, `error`/`errors`/`why` when something went wrong) and `lastSkipped`.
- `/api/mf/status` lists the same runs as `run:refresh-calendars`, `run:refresh-results`, `run:refresh-results-light`.
- The Results calendar page shows "Updated <time> IST" and an amber note on a weekday in results season when the newest result is more than 2 days old.
- On the Latest results page each company without figures says whether it declared today (normal lag) or earlier (still loading, we are retrying), when we last asked and the newest quarter the provider holds for it.

How to read it:
- `lastRun.calendars.status` is `failed` with `error: ... HTTP 4xx/5xx`: the provider call fails (key, plan or outage). `error: the provider sent no rows` or `none with a symbol and a readable date (keys: ...)`: the provider's answer has another shape than the code reads; the keys are listed.
- `lastRun.*.at` is old or null, and `lastSkipped` has a reason: the scheduler is not running the job (read the reason).
- Both are missing: the scheduler is not running (the app container restarted without `scheduler.sh`, or the box is down).
- Jobs run fine but a company stays "still loading" and its note says "its newest is Jun 2026": the provider has not published the quarter. Nothing on our side can fix that; the page keeps asking. If it persists for many companies for more than a day, tell the provider.
- Jobs run, `results.counts.failed` is high and `why` says `rejected`: our data-quality gate refused the new report; see the admin Data health tab.

## Force a refresh now (run on the server)
```
cd /opt/finlit && docker compose --env-file .env.aws -f src/finlit-platform/deploy/aws/docker-compose.aws.yml exec -T app python -m finlit.worker refresh-calendars
cd /opt/finlit && docker compose --env-file .env.aws -f src/finlit-platform/deploy/aws/docker-compose.aws.yml exec -T app python -m finlit.worker refresh-results
cd /opt/finlit && docker compose --env-file .env.aws -f src/finlit-platform/deploy/aws/docker-compose.aws.yml exec -T app python -m finlit.worker refresh-results-light
```
Run them in that order. `refresh-results` and `refresh-results-light` skip a company they asked within the last 50 minutes (longer for companies declared 2 or more days ago), so a second run straight after the first only asks the companies not yet asked.

## Known limits
- Declaration dates have a day, not a time, so "declared today" is the nearest we can get to "declared a few hours ago".
- Whether the provider's quarterly endpoint lags cannot be seen from the code: `providerLatest` on a company (shown on the Latest results page) is the proof.
