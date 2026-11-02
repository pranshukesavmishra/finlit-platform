# Sector pages: Sector Pulse, industry pages, the stock's "Sector & peers", Learn

Founder item 24. Every NSE industry's breadth state (Washout, Thrust C / CAP, Confirmed, Fading, Neutral), one page per industry, a "Sector & peers" section on each stock page and a Learn page.
The numbers come from the `finlit_technicals` package (v2.0.1, vendored in `backend/finlit_technicals/`, changes listed in its `FINLIT_PATCHES.md`), run nightly on NSE's own daily files.
Pages describe price and breadth data; they never advise (no buy / sell / hold wording), carry the package's disclaimer, and put "past averages, not forecasts" beside every study figure.

## 1. Architecture

```
NSE archive ──(fetch-nse, 1 child process, 40 min cap)──> /data/nse            founder's folder, uploaded once
                                                            │  bhav_<year>.csv.gz, idx_<year>.csv.gz, ref/, amfi/
refresh-sectors (bulk job, one at a time)                   ▼
   finlit_technicals batch ───────────────> /data/sectors/releases/.building-<stamp>/   never served
   checks (board, every page, stock files, <5% errors, not far fewer stocks, not an older date)
   os.replace -> releases/<stamp>/ ; symlink `current` swapped in one atomic rename ; older releases pruned (2 kept)
                                                            ▼
website (FastAPI, no pandas) reads /data/sectors/current/*.json  ->  /api/sectors, /api/sectors/{slug}, /api/technicals/{symbol}/sector, /api/sectors/status
```

| Piece | File |
|---|---|
| paths, swap, readers, "not loaded" reason | `backend/finlit/sector_data.py` |
| the job (`fetch`, `build`, `check`, `swap`, `record`, `--import`) | `backend/finlit/sector_job.py`, command `refresh-sectors` in `worker.py` |
| routes and plan gating | `backend/finlit/sector_api.py`, `redact_sector_*` in `backend/finlit/auth/entitlements.py` |
| registry and freshness | `backend/finlit/jobs/registry.py` (job `sectors`), `jobs/freshness.py` (dataset `sectors`) |
| pages | `frontend/src/pages/SectorPulse.tsx`, `SectorIndustry.tsx`, `LearnSectorSignals.tsx`, `stock/SectorPeers.tsx`, `components/sectors/`, `lib/sectors.ts`, `lib/sectorStudy.ts`, `styles/sectors.css` |

Routes: `/sectors`, `/sectors/:slug`, `/learn/sector-signals`; the stock page gets a "Sector & peers" section (`#sector`, after Peers). Sidebar: Markets > Sector Pulse; More > Learn > How sector signals work.

## 2. Plans (enforced on the server, never only in the browser)

| Plan | Sees |
|---|---|
| Basic (and visitors) | the state and breadth bars of every group, the market block, the industry page's chart, number cards and study text, the too-few list, the universe numbers |
| Silver | adds the ranked stock tables, the not-counted lists, the leader-flag counts and the leader-flag list |
| Gold | adds the stock page's "Sector & peers" cards and the peer label column |
| Admin | everything |

Why this split: it follows the repo's own pattern (free = the state of the market, Silver = lists of named companies, Gold = per-company analytics such as the Prism and technical views), and it is the split the founder proposed.
A locked value arrives as `null` and the answer carries `locked: {field: plan}`, so a page says why it is blank. Below Gold the stock answer holds only the stock's name and its industry's state (which every plan sees on the board). Answers differ by plan, so they are `Cache-Control: private` with an ETag (304 on a repeat).

## 3. The nightly flow

`refresh-sectors`, job `sectors` in the registry: bulk, weekdays after 19:00 IST (AFTER_CLOSE window, not before 19:00) and a MORNING catch-up, SLA "session" 14 h (the data for each trading day must be processed after 18:30; overdue 14 h later), after the `technicals` job, memory weight 1500 MB, at most 90 minutes, stall watch 45 minutes. It never runs beside another bulk job. **Off until `SECTORS_ENABLED=1`**; until then the status says "disabledByConfig" and it is never counted as overdue.

1. **fetch** (`SECTOR_FETCH`, default on): one quick request to NSE's archive first; if NSE refuses the server the run says so at once ("NSE's archive refused this server (HTTP 403) ... run the download from a PC in India") instead of waiting minutes. Otherwise `fetch-nse` runs in a child process with a time cap. The newest days are added to `/data/nse`. A failed download never crashes the supervisor; the run carries on with the files it has.
2. **build** into a new folder; the files in use are not touched.
3. **check**: board and every industry page written, stock files, fewer than 5% stocks with an error, not below 80% of the live stock count, not older than the live data. Otherwise nothing is published.
4. **swap** atomically. Any failure or kill leaves the last good set serving.
5. **record**: job log, `last_run.json`, Postgres (`record_run`, key `run:refresh-sectors`, visible at `/api/mf/status`), and `GET /api/sectors/status` (date of data, stocks counted, stock files, errors, how the last run ended and why). `/api/jobs/status` shows the job and the dataset "Sector pulse: board date vs expected session".

Result words: `ok`, `unchanged` (NSE files are what the live set was built from), `behind` (data older than the latest session: retried after 30, 60, 120 minutes; the reason says what the download said), `error` (reason in plain words). Exit code 1 for `behind` and `error` so the supervisor retries and, after three, tells the founder.

When there is nothing to show, every route answers 503 `Sector data is not loaded yet: <why>` (job switched off / first run not finished / the last run's own reason), and every page shows that sentence.

## 4. The NSE data folder (the founder owns it)

About 240 MB: `bhav_2016.csv.gz` ... `bhav_2026.csv.gz`, `idx_2016.csv.gz` ... `idx_2026.csv.gz`, `ref/`, `amfi/`. Nothing else is needed. The job also keeps a cache in it (`.finlit_cache/panel.pkl`, about 285 MB, rebuilt each time the files change).
`fetch-nse` normally relies on the per-day folders (`bhav/<year>/`, `idx/<year>/`) that a PC accumulates. A server given only the 240 MB would have fetched ten years again and then replaced each year file with the few days fetched. Two small patches in the vendored package prevent both (days already inside a year file count as fetched; days only the old year file has are kept). Tests: `finlit_technicals/tests/test_fetch_merge.py`.

### Upload it once (Windows PC to the server)

Docker mounts `/opt/finlit/data/nse` as `/data/nse` (compose file, README). In PowerShell on the PC (replace the key file and address):
```
# 1. on the server, once:
ssh -i key.pem ubuntu@SERVER "sudo install -d -o 1000 -g 1000 /opt/finlit/data/nse /opt/finlit/data/sectors && mkdir -p /tmp/nse-upload"
# 2. copy the folder (this skips the day folders; only the files the job needs)
scp -i key.pem C:\path\nse\bhav_*.csv.gz C:\path\nse\idx_*.csv.gz ubuntu@SERVER:/tmp/nse-upload/
scp -i key.pem -r C:\path\nse\ref C:\path\nse\amfi ubuntu@SERVER:/tmp/nse-upload/
# 3. on the server: move it into place and give the app ownership
ssh -i key.pem ubuntu@SERVER "sudo mv /tmp/nse-upload/* /opt/finlit/data/nse/ && sudo chown -R 1000:1000 /opt/finlit/data && ls -la /opt/finlit/data/nse | head -30 && du -sh /opt/finlit/data/nse"
```
(If the upload is interrupted, run the same `scp` again.) Check the listing shows both sets of years and `ref/`, `amfi/`.

## 5. Settings (in `/opt/finlit/.env.aws`)

| Variable | Default | Meaning |
|---|---|---|
| `SECTORS_ENABLED` | `0` | `1` switches the nightly job on |
| `SECTOR_NSE_DIR` | `/data/nse` | the NSE data folder inside the container |
| `SECTOR_OUT_DIR` | `/data/sectors` | the swap-in folder the website reads |
| `SECTOR_FETCH` | `1` | `0`: do not download; build from the files in the folder (use when NSE refuses the server and you copy files up by hand) |
| `SECTOR_FETCH_MAX_MIN` | `40` | time cap for the download |
| `NSE_DATA_DIR`, `SECTORS_DATA_DIR` | `/opt/finlit/data/nse`, `/opt/finlit/data/sectors` | compose-level: the host folders that are mounted |

## 6. Run it by hand

```bash
cd /opt/finlit/src/finlit-platform
DC="docker compose -p finlit -f deploy/aws/docker-compose.aws.yml --env-file /opt/finlit/.env.aws"
ENV_FILE=/opt/finlit/.env.aws $DC exec app python -m finlit.worker refresh-sectors            # fetch + build + swap
ENV_FILE=/opt/finlit/.env.aws $DC exec app python -m finlit.worker refresh-sectors --no-fetch # build from the files already there
ENV_FILE=/opt/finlit/.env.aws $DC exec app python -m finlit.worker refresh-sectors --force    # even if the files are unchanged
ENV_FILE=/opt/finlit/.env.aws $DC exec app python -m finlit.worker refresh-sectors --import /data/sectors/incoming/site_data   # a set built elsewhere
curl -s https://<site>/api/sectors/status
```
A manual run does not wait for the supervisor's memory gate: check `free -m` first (see section 8).

## 7. When NSE refuses the server

NSE sometimes refuses data-centre addresses. The job then reports it (`/api/sectors/status` > `lastRun.fetch`) and the last good pages keep serving, with the date of their data visible. Remedies, best first:
1. On the founder's PC (India), run the package's own fetch and batch, then send the finished output: `python -m finlit_technicals fetch-nse --dir nse`, `python -m finlit_technicals batch --nse nse --out site_data`, zip `site_data`, copy it to `/opt/finlit/data/sectors/incoming/`, unzip, and run the `--import` command above. This needs no memory on the server at all (see the next section).
2. Or copy the newest `bhav_2026.csv.gz` and `idx_2026.csv.gz` up, set `SECTOR_FETCH=0`, and run `refresh-sectors --no-fetch`.

## 8. Memory and time (measured, synthetic data of the real size)

Measured on a generated folder of the real scale (2,800 stocks, Jan 2016 to Oct 2026, 5.7 million rows; real NSE files have more securities, so expect somewhat more):

| Step | Result |
|---|---|
| building the market panel (load, adjust, pivot) | v2.0.1 as delivered: peak **2,449 MB**; with the two memory patches: peak **1,495 MB**, about 40 s |
| holding the engine (panel + universe) | about 980 MB steady |
| per-stock scores and peer labels, 2,467 stocks | RSS grows from about 960 MB to **1,214 MB** by the last stock; the whole run's peak stays the 1,495 MB of the panel build; 0 errors |
| output on disk | about 76M (one release; two are kept) |
| batch time | about 1.3 to 1.5 s per stock on one core of a fast 4-core machine: **53 minutes** for all 2,467 stocks, start to finish (the package's own figure was 20 minutes; this run shared the machine with the test suites) |
| cached panel on disk | 285 MB |

Honest reading for the t3.small (2 vCPU, about 2 GB, app container limit 1,200 MB): **the job needs about 1.5 GB at its peak, so it does not fit the 1,200 MB app container next to the website.** The registry weight is 1500 MB, so the supervisor's memory gate keeps it waiting ("waiting for memory: ... needs about 1500 MB") rather than starting and being killed; nothing else is affected. The time on the t3.small was not measured (expect longer than the figure above).
Decision for the founder, in order of preference:
* **A. Build on the PC, upload the result (recommended on the 2 GB server).** About 100 MB output, one `scp` and one command (section 7, remedy 1). Also solves NSE refusing the server. Costs a daily manual step (a Windows scheduled task can do the build and upload).
* **B. Give the server more memory**: a 4 GB instance (t3.medium), then change `mem_limit: 1200m` of the `app` service in `deploy/aws/docker-compose.aws.yml` to `2600m` and redeploy; the job then starts by itself each evening.
* **C. Leave the feature off** (`SECTORS_ENABLED=0`): the pages say "Sector data is not loaded yet".

## 9. Things that were not verified offline

A real NSE fetch (the sandbox cannot reach NSE; the refusal path, partial and timeout cases are tested with fakes), the real server's memory and run time, the real NSE folder (a synthetic one of the same size was used), and Caddy/TLS behaviour of the new routes (they are plain JSON routes registered before the site-backend catch-all).

## 10. Failure modes

| What you see | Meaning | What to do |
|---|---|---|
| Pages say "Sector data is not loaded yet: the nightly sector job is switched off" | `SECTORS_ENABLED` is not 1 | upload the folder, set it, restart |
| "... the NSE data folder /data/nse does not exist" | upload not done or mount missing | section 4; check `ls /opt/finlit/data/nse` |
| `behind`: "NSE's archive refused this server" | NSE blocks the address | section 7 |
| `behind` with "NSE had not published a newer file" | normal before about 19:00 or on a holiday | none; retried automatically |
| job state "waiting for memory" | the job needs 1.5 GB | section 8 |
| `error`: "The new set was not published (...)" | a check failed; the old set keeps serving | read the reason; run again with `--force` after fixing |
| a stock shows "Industry not yet classified" | new listing NSE has not classified | picked up when `fetch-nse` can read NSE's website API (it sometimes refuses scripts) |

Rollback of the data: the previous release is kept in `/data/sectors/releases/`; repoint with `ln -sfn releases/<older> /data/sectors/current` (inside the container).

## 11. Known gap

The peer card on the stock page still uses the indicator's peer lists (TradingView groups), so it can name a different group than NSE's industry; the card says so.
