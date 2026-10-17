# Research tools: what each plan gets, and where the data comes from

Written against the "FinLit Technical Improvement & Modernization Plan" (Oct 2026). Plan names are Basic (free), Silver and Gold.

| Tool | Basic | Silver | Gold |
|---|---|---|---|
| **Screener** (`/screener`) | Size, returns, valuation, profitability, growth, debt and sector filters; quick screens; save a screen | + CSV download | + **model filters**: FinLit score, band, five pillars; model quick screens; score columns |
| **Compare** (`/compare`) | 2 companies: Overview, Fundamentals, Spider, Valuation; choose which measures | + model tabs (Quality & Risk, Growth, Technical) and Build your own, pillar radar | up to 4 companies |
| **Watchlist** (`/watchlist`) | preview | up to 3 named lists, 30 stocks, notes, target prices, bucket by industry/size, sector mix, compare selected, CSV | unlimited lists, bucket by FinLit band and style, "worth a second look" signals |
| **Glossary** (`/glossary`) | all 95 terms, A–Z, search, categories, formulas | same | same |
| **Latest quarter** and **Trends** (stock page) | yes | yes | yes |

Plan checks in the browser are a *preview* (the "Preview" switch in the header). Real entitlements must be enforced by the API once accounts and payments ship; the browser never receives data it should not show.

## Data
- **Screener and Compare** read one endpoint, `GET /api/screener/universe`: one row per scored company from the `scores` table (migration `003_screener_columns.sql` adds name, P/B, ROCE, debt/equity, growth, margin and return columns). The browser filters and compares locally, so no request is made per click. About 5,700 rows is roughly 1 MB before compression.
- **Percentiles** ("beats 82% of companies") and the "range most companies fall in" strips are computed in the browser from that same list.
- **Latest quarter / Trends** use the existing `financials` section (`quarterly.pl`, yearly P&L, balance sheet and cash flow), `segments`, `events` and `ratios`. When a new quarter is published, the next ingest run updates them; nothing else changes.
- **Glossary** content is `frontend/src/content/glossary.json`, parsed from the owner's *Finance Glossary A–Z* PDF (95 terms). Categories were assigned by us; the PDF places "Asset Turnover Ratio" under T and "Ex-Dividend Date" under X, and those placements are kept as supplied.
- **Watchlists** are stored in the browser (`localStorage`) until accounts exist; the same shape will sync to the server.

## Demo build
`VITE_DEMO=1` serves saved JSON. Only RELIANCE is a real report. For the screener and comparison the demo adds **fictional** companies (symbols start with `SMP-`) from `frontend/public/demo/screener.json`, clearly flagged on screen. Regenerate with `python backend/scripts/make_demo_universe.py frontend/public/demo`.

## Fonts and security
Fonts are bundled with the site (`@fontsource`), so no request goes to Google Fonts; the Content-Security-Policy no longer allows `fonts.googleapis.com` or `fonts.gstatic.com`.
