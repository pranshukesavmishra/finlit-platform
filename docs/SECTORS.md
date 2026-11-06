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

`refresh-sectors`, job `sectors` in the registry: bulk, weekdays after 19:00 IST (AFTER_CLOSE window, not before 19:00) and a MORNING catch-up, SLA "session" 14 h (the data for each trading day must be processed after 18:30; overdue 14 h later), after the `technicals` job, memory weight 450 MB (measured peak 364 MB, section 8), at most 90 minutes, stall watch 45 minutes. It never runs beside another bulk job. **Off until `SECTORS_ENABLED=1`**; until then the status says "disabledByConfig" and it is never counted as overdue.

1. **fetch** (`SECTOR_FETCH`, default on): one quick request to NSE's archive first; if NSE refuses the server the run says so at once ("NSE's archive refused this server (HTTP 403) ... run the download from a PC in India") instead of waiting minutes. Otherwise `fetch-nse` runs in a child process with a time cap. The newest days are added to `/data/nse`. A failed download never crashes the supervisor; the run carries on with the files it has.
2. **build** into a new folder; the files in use are not touched. The build runs in stages, each in its own process, so none holds the whole market in memory (section 8).
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
| `SECTORS_ENABLED` | `1` | ignored: the nightly job is always on (it waits for memory and for the NSE folder, and says why) |
| `SECTOR_NSE_DIR` | `/data/nse` | the NSE data folder inside the container |
| `SECTOR_OUT_DIR` | `/data/sectors` | the swap-in folder the website reads |
| `SECTOR_FETCH` | `1` | `0`: do not download; build from the files in the folder (use when NSE refuses the server and you copy files up by hand) |
| `SECTOR_FETCH_MAX_MIN` | `40` | time cap for the download |
| `SECTOR_PARTS` | `4` | how many sequential parts the stocks are scored in (section 8); each part is its own process and rebuilds the market universe (about 10 s) |
| `SECTOR_STAGED` | `1` | `0`: run the whole build in one process, as before (needs about 2 GB; only for a bigger server or to compare) |
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

The job used to hold the whole market in one process (about 1.5 to 2 GB) and could not start in the 1,200 MB app container. It now runs in **stages, each in its own process**, and the largest moment of the whole run is **364 MB**. The files it releases are **byte for byte the same** as before.

Measured on a generated folder of the real scale (`finlit_technicals/tests/big_fixture.py`: 2,800 stocks, 2,820 keys after renames, 2,672 days Jan 2016 to Oct 2026, 5.76 million rows, 2,270 stocks scored; real NSE files have more securities, so expect somewhat more). Same machine, same folder, the code of commit `80a422e` against the new code, started the same way (`sector_job.default_batch`), memory sampled from `/proc` every 0.25 s:

| | before (one process) | after (stages) |
|---|---|---|
| largest memory of any one process | **2,038 MB** | **342 MB** (the panel stage) |
| largest total of all processes at one moment (the job process counts) | 1,995 MB | **364 MB** |
| of which anonymous memory (the rest is shared libraries and memory-mapped file pages the kernel can drop at any time) | 1,965 MB | 298 MB |
| total time, one core at a time | 47 min (2,812 s) | 49.5 min (2,968 s) |
| files released | 2,316 | 2,316, **all byte for byte identical** (`measure_job.py compare`) |

(The package's own earlier figure for the same step was 1,495 MB; on this folder and with pandas 3.0 the single process reached 2,038 MB. Either way it does not fit.)

The stages, with the peak of each process and its time (`stages:` lines in the job log):

| Stage | What it does | Peak | Time |
|---|---|---|---|
| panel | reads the yearly bhavcopy files one at a time (twice: days to drop, keys and ISIN links, then each year's rows), writes the panel as `.npy` files in `<nse>/.finlit_cache/panel/` | 342 MB | 42 s (skipped when the cache is current) |
| prepare | opens the panel memory-mapped, builds the whole-market universe month by month, chooses the stocks, splits them into 4 parts by industry group | 268 MB | 10 s |
| score x 4 | per part (about 567 stocks): the same per-stock work as before, with the whole-market universe rebuilt in that process (so every stock is judged against the full market) | 270 to 299 MB | 12 min each |
| merge | the board (counts, ordering, "too few stocks" lists), every industry page with all peer labels, `_summary.json` | 284 MB | 11 s |

What was changed, and why the answers cannot change: the panel is built a year at a time and kept as plain `.npy` files that are opened read-only with `mmap` (only the pages in use are resident; the cache signature is unchanged and a stale or half-written cache is rebuilt); the universe rules are applied to blocks of stocks (each stock is judged on its own numbers plus two market-wide series that are worked out once) and keep only the last day's inputs (the only day the explanations read); the stocks are scored in four sequential child processes, and the merge process sees every group and every peer label. No value is rounded, shortened or estimated: `float32` was **not** introduced anywhere (the adjustment factors, `cum`, and everything computed from them stay `float64`; the arrays that were `float32` stay `float32`). The list of changes to the package is in `finlit_technicals/FINLIT_PATCHES.md` (6 to 12).

The proof: `finlit_technicals/tests/test_staged_equals_single_run.py` runs a frozen copy of the old code (`tests/reference_v201/`) and the new job on the same synthetic folder and compares every panel array bit for bit and every released file byte for byte (`_summary.json` without its clock fields); the same comparison at the real size is `python finlit_technicals/tests/measure_job.py compare OLD_OUT NEW_OUT` (the numbers above). To measure again: `big_fixture.py DEST` builds the folder, `measure_job.py run --tree BACKEND_DIR --nse DEST --out OUT` runs a tree's job and samples its memory.

| Other figures | |
|---|---|
| output on disk | about 69 MB (one release; two are kept) |
| cache on disk | 267 MB (`.finlit_cache/panel/`; it replaces the 285 MB `panel.pkl`, which is deleted at the first rebuild) |
| time per stock | about 1.3 s on one core of this 4-core machine; the t3.small (2 vCPU, burstable) was not measured: expect longer, the job limit is 90 minutes |
| failure of a stage | the run stops with the stage's name and last lines in the status ("the 'score' step was killed (most likely out of memory)"), the previous release keeps serving |

Reading for the t3.small (2 vCPU, about 2 GB, app container limit 1,200 MB): **the job fits.** Its registry weight is 450 MB (the measured 364 MB plus a margin for real NSE files having more securities), so the supervisor's memory gate starts it when 550 MB (weight + the 100 MB left for the site) are free and otherwise shows "waiting for memory".
Limits of this measurement: the data is synthetic (same size, not the same values); the machine is faster and has more cores than the t3.small; the real NSE folder has more securities, so expect somewhat more (the margin in the weight is for that). The "before" run shared the machine with the "after" run and the test suites (each job uses one core of four), so its time is slightly pessimistic. The page cache of the server will hold part of the 267 MB panel files; it is reclaimable and is not counted above.
Building on the founder's PC and uploading the result (section 7, remedy 1) still works unchanged and is the answer when NSE refuses the server's address.

## 9. Things that were not verified offline

A real NSE fetch (the sandbox cannot reach NSE; the refusal path, partial and timeout cases are tested with fakes), the real server's memory and run time, the real NSE folder (a synthetic one of the same size was used), and Caddy/TLS behaviour of the new routes (they are plain JSON routes registered before the site-backend catch-all).

## 10. Failure modes

| What you see | Meaning | What to do |
|---|---|---|
| Pages say "Sector data is not loaded yet: the nightly sector job is switched off" | `SECTORS_ENABLED` is not 1 | upload the folder, set it, restart |
| "... the NSE data folder /data/nse does not exist" | upload not done or mount missing | section 4; check `ls /opt/finlit/data/nse` |
| `behind`: "NSE's archive refused this server" | NSE blocks the address | section 7 |
| `behind` with "NSE had not published a newer file" | normal before about 19:00 or on a holiday | none; retried automatically |
| job state "waiting for memory" | the job needs about 550 MB free (450 + 100 for the site) and something else is using it | none: it starts by itself when memory is free (section 8) |
| `error`: "The new set was not published (...)" | a check failed; the old set keeps serving | read the reason; run again with `--force` after fixing |
| a stock shows "Industry not yet classified" | new listing NSE has not classified | picked up when `fetch-nse` can read NSE's website API (it sometimes refuses scripts) |

Rollback of the data: the previous release is kept in `/data/sectors/releases/`; repoint with `ln -sfn releases/<older> /data/sectors/current` (inside the container).

## 11. Known gap

The peer card on the stock page still uses the indicator's peer lists (TradingView groups), so it can name a different group than NSE's industry; the card says so.

## 12. Sector Rotation and the 2.4.1 package (5 Nov 2026)

`finlit_technicals` is now 2.4.1 (`backend/finlit_technicals/FINLIT_PATCHES.md`, "Installing 2.4.1"). It fixes the Fading rule (a fade is set once, so Fading lasts 20 sessions), counts stocks on the same base everywhere (`stocks_counted` = members with a price on the last session, `members_not_traded_today` = the rest), names a one-industry sector group after the industry (Capital Goods became **Agricultural Commercial & Construction Vehicles**), and adds Sector Rotation.

**Files.** The nightly job writes, inside the release: `rotation/_map.json`, `rotation/<slug>.json`, `rows[].rotation` in `sectors/_board.json`, `sector.rotation` in every stock file, and `sector_corner`, `sector_rotation_rank`, `sector_rank_change_1w` in `_summary.json`. In the staged job the rotation is worked out in the merge stage (it ranks every group, which a score part cannot see) and added to the stock files and summary lines; the bytes equal the single-process run (`test_staged_equals_single_run`). If rotation fails the run still publishes without it and the Rotation page says why it is blank (`/api/sectors/status` has `rotationLoaded`).

**Renamed groups and old files.** The build goes into a NEW folder and is swapped in, so a file of an earlier release (`sectors/capital-goods.json`, `rotation/capital-goods.json`) cannot be in the new one. A folder uploaded with `--import` is cleared of page files its board and map do not list (`sector_job.clear_orphans`). `/sectors/capital-goods` redirects in the website, and `/api/sectors/capital-goods` and `/api/rotation/capital-goods` answer with the renamed group (`sector_data.SLUG_ALIASES`). Changing the package version changes the job's signature, so the next run rebuilds even when NSE's files are unchanged.

**API (every plan).** `GET /api/rotation` (the page) and `GET /api/rotation/{slug}` (one card) read the nightly files, like the other sector routes (no pandas in the website, so there is no live-compute fallback: a missing file answers 503 "Rotation data is not loaded yet: ..."). Rotation is open to every plan, as the states and breadth of Sector Pulse are; only the leader-flag count each row carries follows the board's Silver rule (`redact_rotation_map`). The Basic stock teaser carries `rotation` (group-level figures).

**Alerts.** Two built-in alerts for the industries of watchlist stocks (Silver and Gold, like the other built-in alerts): the industry moved corner, and the industry climbed or fell 5 or more places in 4 weeks (new this week). Preferences `rotationCorner` (on by default) and `rotationRank` (off by default), both on the Account page. They are worked out from the rotation file alone (it holds weeks in the corner, the corner it came from and 26 weeks of ranks), sent once after a week's last session (`week_closed`), deduped in `auto_alert_sent` (`finlit/rotation_alerts.py`).

**Not wired: the screener.** The screener table is built from the database (`screener/data.py`, versioned metric rows and delta sync), not from the sector release, so `sector_corner`, `sector_rotation_rank` and `sector_rank_change_1w` in `_summary.json` have no path into it. It needs a loader that overlays those three fields from `current/_summary.json` onto the table by symbol, three catalogue entries (rank, 4-week change, and the corner as a coded facet) and the filter chips; that is a change to the screener core and is left for its own piece of work.

**Data checks (section 4 of the package).** `python scripts/check_universe_inputs.py ASHIANA SURAJEST MAHSCOOTER TVSHLTD DPABHUSHAN MIDWESTLTD OMNI --nse /data/nse --days 8` prints, per stock, the series and traded value (Rs crore) the job read for the last sessions next to the same rows read straight from the yearly file, the 65-session median that the universe rule compares with Rs 2 crore (join) and Rs 1 crore (stay), and when the stock joined or left the counted list. Read in the code: the series column is read by `fetch.parse` for all three NSE formats (a test file for each gives EQ/BE as expected) and traded value is `TtlTrfVal` / `TOTTRDVAL` / `TURNOVER_LACS x 1e5`, all in rupees, so no defect could be proved from the code. Note the hysteresis: a stock that joined at Rs 2 crore or more stays while its median is Rs 1 crore or more, so ASHIANA at Rs 1.41 crore can be correctly counted if it joined earlier; the script shows whether it did. The five stocks marked "not in the EQ series" on 4 Nov: compare the `panel series` and `file series` columns for 4 Nov; BE there means NSE moved them to the trade-for-trade series that day.

## 13. A build longer than one run (6 Nov 2026)

What went wrong: on the server the full build took about 2 h 33 min (the run of 4 Nov, started by hand). The job may run 90 minutes, so from 5 Nov every scheduled
run was stopped part-way and the next one started again from zero: 11 stops in a row, the job held, and 2.4.1 (the corrected states) and the Rotation files
never reached the live site (`/api/sectors/status` showed `rotationLoaded: false`, `/api/rotation` answered 503).

The fix: the job is **resumable**. The build folder is `releases/.building-resume-<signature>` (the signature covers every NSE file and the package version),
and it is kept when a run is stopped; the staged runner keeps its plan and every finished score part (`part-<k>.pkl`) next to it. The next run, 2 minutes
later, skips what is done and builds only the rest; the released files are byte for byte those of an uninterrupted run
(`test_a_stopped_run_continues_with_its_finished_parts_and_gives_the_same_files`). New NSE files give a new signature, so nothing is reused across inputs;
a kept folder older than 30 hours is deleted. `SECTOR_RESUME=0` turns this off. The job now also has the NIGHT window, so it runs through the night shift.

Running it by hand (server window, `ubuntu@ip-`) still works and needs no time limit:
`docker compose -p finlit -f deploy/aws/docker-compose.aws.yml --env-file /opt/finlit/.env.aws exec app python -m finlit.worker refresh-sectors --no-fetch`.
