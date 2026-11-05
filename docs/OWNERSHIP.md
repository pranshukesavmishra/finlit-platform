# Ownership insights (company page, section 11)

The Ownership section (`/stocks/SYMBOL`, anchor `#ownership`, nav entry unchanged, open to every visitor like before) is drawn from two stored things:

| Part of the page | Read from |
|---|---|
| Year chips, "Owners today", "Who bought and who sold", the four line charts, "Show the numbers", CSV | the stored shareholding, `GET /api/stocks/SYM/ownership` (every quarter the provider reports, so the year selector keeps every year) |
| "What changed, in short" (cards, Show more, quiet text), "Also from the filing", "Largest institutional holders", the share-count rule | `GET /api/stocks/SYM/ownership-insights`: the output of `finlit_technicals.ownership.analyse()` |

The page NEVER calls the premium fundamentals endpoint (40 s or more for a company it has not cached).

## Package

`backend/finlit_technicals/ownership.py` is the team's `finlit_technicals` 2.3.2 module, taken alone (pure Python, standard library only). The rest of the 2.3.2 package differs from the vendored 2.0.1 in files FinLit patched (`nse.py`, `fetch.py`, `sectors.py`, `universe.py`, `batch.py`, see `FINLIT_PATCHES.md`), so it was not replaced: the sector pages are untouched. Also added: `tests/test_ownership.py` and `tests/fixtures/ownership.json` (11 tests, run by `tests/run_tests.py`, 70 in all), and the `ownership` command hook in `__main__.py`. Version string stays 2.0.1.

## Data flow

1. Ingest stores the `ownership` section (quarterly series per group).
2. Job `ownership-insights` (`python -m finlit.worker refresh-ownership`, light lane, priority 47, SLA 36 h, always on, `finlit/ownership_insights.py`):
   * pass 1, database only: every company with a stored shareholding gets a row in `ownership_insights` (migration 090); a row whose `as_of` differs from the newest stored filing is built again from the stored shareholding and the kept premium part;
   * pass 2, the slow call: `GET {SITE_API_URL}/api/stocks/admin/fundamentals?query=SYM` with the gateway token (as `finlit/premium.py` and Prism do), 3 at a time (`--concurrency`), 120 a run (`--limit`), nothing new started after 20 minutes (`--max-minutes`). Companies a visitor opened without a premium part (Redis `ownership:wanted`) go first, then companies with none, then those with a newer filing than the kept figures, then those older than 25 days. A failed call is tried again after 6 hours. Resumable: the next run continues with what is missing.
   * `ownership.pack_from_site(ownership_json, premium_json)` builds the pack; only its `structure` and `holders` are kept (`extra`), so a row can be rebuilt with no call.
3. `GET /api/stocks/SYM/ownership-insights` reads the row. If the stored shareholding has a newer filing than the row, or there is no row, it builds one at once from the stored shareholding (pure, cheap), saves a missing row and queues the company in `ownership:wanted`. A page is never empty and never waits for the provider.
4. Data-freshness dataset `ownership`: the last completed run of the job (under 40 h fresh, 96 h stale).

## Blanks and their reasons

The response carries `premium: {state: ok|missing, reason, has: {structure, holders}}`. When `missing`, the section still shows everything drawn from the shareholding and "Also from the filing" shows the reason instead of numbers:

* not yet fetched ("fetched overnight, appear after the next run"), 
* the provider connection is not set up on this server (no `SITE_API_URL` or `CMS_JWT_SECRET`),
* the provider has no figures for this company,
* the provider did not answer the last time (HTTP status or error kind named; retried automatically).

Per field: shareholders, pledge, share count, lock-in come from `ownershipStructure`; named holders from `shareholdingDetails`; each shows its own "not in the data" reason if only that field is empty. Cards: when no rule fires the page shows `quiet_text`.

## Page rules kept from the handover

Group colours are the five fixed hexes; everything else uses the design tokens. Tone is icon plus word. Bought/Sold only when the share count for the two filings is known and moved less than 0.5%; otherwise Up/Down with a note; a missing count says so. Every chart label is page text (no text inside an SVG). Line charts: own y-scale, at least 4 pts tall, 8% padding, ticks every 1, 2, 5 or 10 (first step with at most four), hollow start dot, filled end dot, Government not charted (the note gives its share). No buy, sell or hold calls. Code: `frontend/src/stock/own/`, `frontend/src/lib/ownView.ts`.
