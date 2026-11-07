# Diversification card

Spec: the addendum "Mode B without amounts" (3 Nov 2026). The card describes how a list of stocks has moved together. It takes share names only and never advises.

- Endpoint: `POST /api/diversification` with `{symbols, benchmark: "NIF50", horizon: weekly|monthly|yearly}`. Any other field, or a bad horizon, is a 422. 1 to 100 names; fewer than 3 stocks with 52 weeks of prices give Spread by count only.
- Code: `backend/finlit/diversification/` (`calc.py` the maths, `sectors.py` + `data/macro_sector_map.json` the macro-sector map, `data/business_groups.json` the group tag, `api.py` the route). Frontend: `frontend/src/components/diversification/`.
- Data: stored adjusted weekly closes (`price-MAX`), NIFTY 50 daily closes reduced to ISO weeks. The unfinished current week (and month) is dropped. Cached in Redis by sorted names + unfinished week + horizon for 6 hours.
- Score: since the Equity portfolio redesign the score, its two parts and "moves like N" come from the Equity portfolio engine (`finlit/portfolio_page`, 104 weekly returns, plain correlations, NSE sector labels): see docs/PORTFOLIO-PAGE.md. `calc.py`'s own 156-week score is kept for its tests and is not shown. Formerly: 0.6 co-movement + 0.4 sector spread, `scoreVersion` "1", always on weekly 156 weeks. Bands come from the rounded score.
- Plans: the endpoint is open (like Compare and the stored prices); Equity portfolio keeps its Silver gate. The style tilt comes from FinLit Prism and is sent to Gold only (`STYLE_TILT_TIER` in `api.py`).
- Maintain: add or fix a group member in `data/business_groups.json`; a Sector label that lands in "Not classified" is fixed in `data/macro_sector_map.json`. No code change.
- Tests: `backend/tests/test_diversification_calc.py` (reference snapshot), `test_diversification_api.py` (needs Postgres + Redis), `frontend/src/components/diversification/*.test.tsx`.
