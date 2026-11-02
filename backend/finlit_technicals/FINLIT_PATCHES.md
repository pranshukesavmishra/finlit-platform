# Changes FinLit made to the vendored finlit_technicals v2.0.1

The package is the team's delivery (`finlit_technicals-2.0.1`). It is vendored here unchanged except for the three small, tested changes below.
If a newer version is dropped in, re-apply them (or ask the package authors to take them in) and run `python finlit_technicals/tests/run_tests.py`.

1. `batch.run(..., engine=None)`: accepts the `SectorEngine` the caller already built, so the market panel is held once in memory
   (`nse_symbols(SectorEngine(src))` followed by `run(...)` built two). Default behaviour is unchanged.
2. `fetch.py`, `fetch_days`: a day that is already inside a joined `bhav_<year>.csv.gz` counts as fetched, and a weekday before the last month that is missing from
   the joined files counts as a holiday. Without this a server given only the joined year files (the 240 MB set) would fetch ten years again from NSE.
3. `fetch.py`, `join_years`: days that are in an existing joined file but have no day file are kept when a year is joined again. Without this the first
   `fetch-nse` on such a server would replace a whole year's history by the few days fetched since. On a PC that holds every day file the result is identical.

Tests for 2 and 3: `finlit_technicals/tests/test_fetch_merge.py`.

4. `nse.py`, `drop_repeated_days`: the same rule (a day whose EQ rows repeat the previous day is dropped), but each row is reduced to a 64-bit hash and only the
   previous kept day is held, instead of a Python set of tuples for every day. On ten years of NSE files that set alone took about 1.5 GB and set the peak
   of the whole run (2.4 GB). The days dropped are identical (`tests/test_nse_memory.py` compares with the original code).
5. `nse.py`, `load_bhav`: one shared string object per distinct symbol, series and ISIN instead of one per row. Same values, far less memory.

Measured on a synthetic folder of the real size (2,800 stocks, Jan 2016 to Oct 2026, 5.7 million rows): the peak while the market panel is built fell from
2,449 MB to about 1,490 MB. The numbers and the rest of the measurements are in docs/SECTORS.md ("Memory and time").
