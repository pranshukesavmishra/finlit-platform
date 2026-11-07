# MF portfolio (My mutual funds)

Page `/mf-portfolio` (nav: Workspace > MF portfolio), code `backend/finlit/mfportfolio/` (parse, match, calc, api), migration `079_mf_portfolio.sql`, frontend `pages/MfPortfolio.tsx`, `lib/mfPortfolio.ts`, `lib/mfStatement.ts`.
Descriptive only: no buy / sell / hold / switch / redeem wording. "Information only, not investment advice." and "Describes the fund's health from its past NAVs, costs and holdings; not a recommendation." are shown.

## Data model
`mf_holdings` (id, user_id -> users ON DELETE CASCADE, code = AMFI scheme code, folio '' when none, UNIQUE(user_id, code, folio)) and `mf_holding_lots` (units numeric(20,4) > 0, invested numeric(20,2) NULL = unknown, bought_on date NULL). NAV, returns, expense ratio, size and score are never stored: read from `mf_schemes` / `mf_scores` per request. Every query filters on the member's id.

## API (`/api/me/mf-portfolio`, signed in, Silver or Gold or admin; Basic 403 plan_required; writes need Origin + CSRF)
GET (list + summary + allocation + concentration), POST (add; same scheme+folio adds a purchase), PUT /{id} (replace folio and purchases), DELETE /{id}, POST /import-preview, POST /import-commit. Rate limits per member: writes 120/10 min, preview 30/10 min, commit 20/10 min. Import bodies may be up to 2 MB (2,000 rows); every other route keeps the 64 KB cap. Responses are `private, no-store`.

## Plan gating
The Health Score and its four parts are Gold (admin sees all). Below Gold the server returns every holding with value and returns but `score = {locked: true, ...null}` and does not read `mf_scores`; the summary score is locked too. The page only draws the lock. Limits on funds (entitlements `mf_holdings`): Basic 0, Silver 30, Gold 500 (same as Equity portfolio). A downgraded member keeps the funds and loses the score.

## Import
The browser reads the file with the stock portfolio's reader (xlsx, xls, csv, tsv, HTML table; 5 MB; 2,000 fund rows) and finds columns by header synonyms (scheme/fund name, folio, units / closing unit balance, NAV, cost value / invested, current / market value, ISIN, AMFI / scheme code, purchase date, asset type); headers read are shown. Title lines, section lines, totals and repeated headers are skipped. The server reads the cells (Indian grouping, Rs / rupee sign, brackets, dd-mm-yyyy, Excel serial dates) and:
- ignores company shares (ISIN starts INE, asset type share/bond, company name without fund wording), zero units; rejects missing units and negative units (redemption lines of transaction statements). A missing cost is unknown, never 0. Units keep 4 decimals, money 2 (half up).
- matches in order: AMFI code, ISIN (also IDCW re-investment ISIN), exact normalised name narrowed by the plan (Direct/Regular) and option (Growth/IDCW) the file states, then fuzzy (Jaccard >= 0.7 on name words). Fuzzy and ambiguous names (no plan/option on a fund with several) are only "needs choosing" with a candidate dropdown; nothing is guessed. AMFI/ISIN disagreements, or a code whose scheme name does not resemble the file's name, are also "needs choosing". Not found rows have a fund search.
- Duplicates: an identical line (same fund, folio, units, amount, date) in one file counts once; same fund + same folio otherwise are purchases of one holding; a different (or blank vs filled) folio is a separate holding. A fund+folio already held is skipped by default (re-importing never double counts) or replaced if the member chooses.
- Commit takes only rows with a chosen scheme, revalidates everything, checks the plan limit for the whole import and writes in one transaction (all or nothing).

## Maths
Current = units x latest NAV (NAV date shown; a stopped scheme or an older NAV is flagged). Gain = current - invested, % of invested; only when cost is known and > 0. XIRR uses `finlit.mf.xirr` (spreadsheet XIRR): purchases out on their dates, current value in on the NAV date; needs every purchase dated and costed, no date after the NAV date, first purchase >= 365 days old; a single purchase is CAGR. Summary totals: gain covers only funds with both cost and value (stated on the page); portfolio XIRR covers funds that qualify; weighted Health Score (by current value, Gold) only if every fund is scored. Weight = share of valued funds' current value. Concentration text is descriptive (largest fund, top three, one fund house).

## Limits / unverified
Rows per import 2,000, file 5 MB, 200 purchases per holding. Real CAMS / KFintech files were not available: header synonyms and the sample layouts are modelled on typical exports and need checking against real files. Line numbers in the review count non-blank lines. Migration number 079 (078 is the presets migration); migrations run automatically at app start (`Store.migrate`).
