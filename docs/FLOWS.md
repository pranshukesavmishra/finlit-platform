# FII / DII institutional flows

`GET /api/flows` returns the `Flows` payload of `frontend/src/lib/flows.ts`. Code: `backend/finlit/flows_sources.py` (pure parsers),
`backend/finlit/flows.py` (store, nightly job, payload, route), migration `046_flows.sql`, tests `backend/tests/test_flows.py`
with recordings in `backend/tests/fixtures/flows/`. Same pattern as `macro.py`: steps fail independently and keep the last good data.

## Sources (all public, plain GET or the site's own date form, User-Agent `FinLit-data/1.0 (+https://finlitventures.com)`)

| Id | What | URL | History |
|---|---|---|---|
| `fii` | FPI (FII) cash-market equity buy / sell / net, Rs crore, stock-exchange route; all-asset view (debt, hybrid, MF, AIF, total, US$ mn, rate) | NSDL FPI Monitor `https://www.fpi.nsdl.co.in/web/Reports/Latest.aspx`, `Monthly.aspx`, `Archive.aspx` (the site's "To Date" form returns every reporting day of the month up to the date) | stored from Jan 2010 |
| `dii` | DII cash-market equity buy / sell / net, stock-exchange route: banks, insurance, mutual funds, AIFs, others | NSDL `https://www.fpi.nsdl.co.in/web/Users/DIIGenerateReport.aspx?Rep=L` (latest) and `?Rep=A` ("Enter Date" form, one day) | **from 1 June 2026 only**; NSDL has nothing earlier |
| `participant-oi` | Futures and options open interest (contracts) of FII, DII, Pro, Client | `https://archives.nseindia.com/content/nsccl/fao_participant_oi_DDMMYYYY.csv` (plain CSV, one per trading day; the host answers an honest UA) | last ~150 days kept; page shows the latest day |
| `nifty` | Nifty 50 daily closes for the correlation | FinEdge via `indices._fetch_levels` (same code as `/api/indices/NIF50/history`) | 5 years |
| `nse-cash` | The exchanges' own FII/DII cash report | not used | `unavailable`: nseindia.com / bseindia.com do not answer an honest identified client (bot protection, which we never get around) |
| `manual` | A day typed in by an administrator | see below | |

Probed and not useful: SEBI's MF statistics page (mutual funds only, one day, already inside NSDL's DII), CDSL (no FPI statistics pages found),
AMFI (no daily equity flow), `archives.nseindia.com` other paths (no cash-market FII/DII file exists there; `fii_stats_*.xls` is derivatives turnover).
`robots.txt` of `www.fpi.nsdl.co.in` redirects to an HTML page and of `archives.nseindia.com` is a 404: no rule disallows these paths.

## Definitions
* **Equity flow = stock-exchange route** (secondary market) for both FII and DII, as the exchanges' reports measure it. The primary-market route
  (IPO/QIP allotments) and the two-route sub-total are kept apart; `fpi.equityNet` is the sub-total (both routes), alongside debt and hybrid.
* `fpi.usdMillion` = total net in US$ mn; `fpi.inr` = the rupees-per-dollar rate NSDL converted at.
* Options open interest: calls and puts added together (long = held long, short = written); `net` = long - short.
* Streak, velocity, last30, mood, `fiiShareOfSelling` (a fraction 0..1), `combinedNet`, correlation: as specified (correlation = Pearson of daily net
  with the Nifty 50 same-day % change, from 30 common sessions).
* A window sum (period, month, year) is given only when every session in it has the figure; a part-sum is never shown. DII totals therefore
  show null for windows reaching before 1 June 2026. `index` (optional) is the Nifty close over the same sessions as `days`.
* NSDL's daily figures are provisional and revised; the job re-reads the current and previous month nightly. Rows with a net that is not
  purchases minus sales, out-of-range amounts or future dates are left out at publish time.
* No number is ever estimated; unavailable = null and `sources[]` says so.

## Running
* `python -m finlit.worker refresh-flows [--full] [--only fii dii oi nifty] [--max-age-hours N]`. The first run loads the missing months of FPI
  history (one request per month, paced 1 s; about 30 minutes) and every DII day since June. Boot step and 19:10 IST nightly + 21:30 retry in
  `deploy/scheduler.sh` and `deploy/crontab`.
* Storage: `flows_daily` (per side `*_source` = `nsdl` | `manual`), `flows_oi`, `flows_index`, `flows_meta` (published payload, step runs). Redis hash `flows:v1`, ETag/304.

## Manual entry (optional)
Administrators (with MFA) can type in a day from the exchange's published FII/DII report:
`POST /api/admin/flows` `{"d":"2026-10-22","fii":{"buy":9000,"sell":12000},"dii":{"net":3100.25}}` (give net, or buy and sell). Rows are labelled
`manual` in `sources[]`, replace NSDL's figure for that side and day, and are never overwritten by the nightly job.
`DELETE /api/admin/flows/{date}?side=fii|dii|both` removes manual figures only.

## Adding another DII or FII feed
Write a pure parser in `flows_sources.py` returning `Leg(buy, sell, net)` per day, add a step to `STEPS` in `flows.py` that saves with a new
source label (extend the `CHECK` constraints in a new migration), and add a `sources[]` note. Only permitted official sources; if a feed needs
a captcha, bot-check bypass or a browser disguise, do not use it.
