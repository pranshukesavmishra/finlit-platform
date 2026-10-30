# Back-testing the outlook model

The weights are proposed starting values, not optimised. Before relying on them, run the back-test and review it as a team. Nothing from it is published on the site.

```
cd backend
DATABASE_URL=... REDIS_URL=... python scripts/outlook_backtest.py --statement consolidated --limit 800 > ../docs/outlook/backtest-latest.md
```

For every company with at least 4 stored years, every origin year (from the 3rd year on) and each horizon (1, 3, 5 years) whose target year is stored, `finlit/outlook/backtest.py`:
1. cuts the company's history at the origin year (no later data is used),
2. computes the sector inputs as of that year from the peers' own histories (same functions, same minimum of 5 peers, industry then sector),
3. forecasts with the default weights of the horizon,
4. compares the estimate for the last year of the horizon with the reported figure.

Tables: by horizon; by horizon and sector; by horizon and size bucket (SEBI large/mid/small). Columns: forecasts, MAE (Rs crore), MAPE %, median APE %, bias % (positive = estimates ran high), and "few" under 30 forecasts. MAPE skips years where the actual was not positive.
Caveats: the stored history is short for many companies (long horizons have fewer rows); profit errors are large for lumpy earnings; restated figures are used as stored. Review out of sample (hold back later origin years) before changing any weight. Pure functions are tested in `backend/tests/test_outlook.py`.
