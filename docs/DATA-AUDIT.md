# Data audit: where is data missing, stale, or the wrong kind?

One read-only command that checks every feature of the site against the real tables and tells you what is empty, old, or nonsense. Run it once on the
server and send back the output (text or screenshot) or `/tmp/audit-data.json`.

## Run it (on the server)

    bash /opt/finlit/src/finlit-platform/deploy/aws/deploy.sh compose exec app python -m finlit.worker audit-data

Options (add them after `audit-data`):

- `--quick`: smaller samples, no heavy checks (roughly half the time).
- `--only funds stocks`: only these groups. Groups: `stocks screeners funds etfs indices commodities macro flows news logos dhan jobs keys`.
- `--json /path/file.json`: where the JSON copy goes (default `/tmp/audit-data.json`, inside the container).

To copy the JSON out: `bash /opt/finlit/src/finlit-platform/deploy/aws/deploy.sh compose exec app cat /tmp/audit-data.json > audit-data.json`

The exit code is always 0, even when it finds problems or cannot reach the database. It is not scheduled; nothing runs it but you.

## How to read it

One line per finding, worst first: `WRONG`, `MISSING`, `STALE`, `UNCHECKED`, `OK`.

| Severity | Meaning |
| --- | --- |
| WRONG | a value of the wrong kind: zero or negative price, NAV 0, date in the future, score outside 0-100, absurd P/E or ROE, duplicate or badly written symbol, orphan row, number stored as text |
| MISSING | a table is empty, or a key column is empty in more rows than its allowance, or a related table has no row for many companies/funds |
| STALE | the newest row is older than the feature's cadence, or a scheduled job is overdue or failing |
| UNCHECKED | `could not check: ...` a table or column does not exist, or a query hit the 20 second limit |
| OK | rows and newest date within the cadence (one line per table) |

Columns: feature, what, count (`n of total`; `~` = measured on a random sample), up to 3 example keys, and a one-line likely cause or the command to run.
Provider keys are shown only as True/False; no secret, and nothing from the users table beyond a count of accounts.

## What it checks

Stock pages (company list, scores, stored report sections such as ratios, ownership, events, peers, segments, daily prices, live quotes, quarterly
results, Prism ratings, provider-vs-report mismatches, leadership labels, earnings calls), screeners (prebuilt screen cache, momentum/growth scores, ATH and
price position, industry breadth), mutual funds (schemes: NAV freshness, 1/3/5-year returns, SIP, AUM, risk figures; monthly and daily NAV history, fund
facts, TER, Health Score, Fund Screener figures and holdings, monthly portfolio files, industry report), ETFs, index members and heatmap coverage,
commodities (Redis `cmd:mcx`, `cmd:intl`, `cmd:hb`, `cmd:cfg` and the Dhan contracts), macro series, FII/DII flows (including how far back each starts),
news, filings, results and IPO calendars, logos, Dhan instruments, indices and option lots, every scheduled job (never ran, overdue, failing, switched
off), and which provider settings are set.

## How gentle it is

Read-only transactions, `statement_timeout` 20 s per query, one query at a time on one connection, big tables sampled (about 50 000 rows, 10 000 with
`--quick`), counts capped at 100 000, and no new query starts after 100 s. A failing check never stops the run.

## What it cannot see

- Anything the live provider has but we never stored; it does not call any provider.
- Whether a number is right, only whether it is plausible (ranges are in `backend/finlit/dataaudit.py`, one line each).
- Rows outside the sample on very large tables (price history, NAV history): a rare bad row can be missed; it reports `~` counts.
- JSON fields inside stored report bodies, apart from emptiness and the metrics column.
- Thresholds for "empty beyond a sensible share" are judgement calls (for example only the top companies are loaded in full); tune them in the spec.
