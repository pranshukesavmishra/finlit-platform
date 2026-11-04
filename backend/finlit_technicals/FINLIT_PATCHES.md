# Changes FinLit made to the vendored finlit_technicals v2.0.1

The package is the team's delivery (`finlit_technicals-2.0.1`). It is vendored here unchanged except for the small, tested changes below (1 to 5, then the staged job, 6 to 12).
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


## The staged job: the nightly run fits the 1,200 MB container (patches 6 to 12)

Rule for all of these: **the answers do not change**. The files released are byte for byte those of the single-process code above (patches 1 to 5), proven by
`tests/test_staged_equals_single_run.py` against a frozen copy of that code (`tests/reference_v201/`, do not edit) and, at the real size, by `tests/measure_job.py`
(numbers in docs/SECTORS.md, section 8).

6. `nse.py`, `build_panel_files` (used by `NseHistory.panel`): the market panel is built one yearly file at a time (a first pass for the days to drop, the keys and the ISIN
   links, which need the whole history; a second for each year's rows) and written as plain `.npy` files (one stock after the other, so a stock's history is one piece of the file) in `<nse>/.finlit_cache/panel/`, then opened read-only with
   `mmap_mode="r"`; the pages are given back (`release_mapped`) after each year, block of stocks and a few stocks scored. The old cache was one pickle (`panel.pkl`) that had to be loaded whole. Yearly files that overlap in dates, or a cache folder that cannot be written,
   fall back to the old in-memory build (`NseHistory(..., chunked=False)` forces it). Same dtypes, same numbers, bit for bit. A cache without its `meta.pkl` (a build that never
   finished), with a file cut short, or built from other files (the signature logic is unchanged) is rebuilt.
7. `nse.py`, `adjustment_blocks`: the adjustment factors are worked out for blocks of stocks (every stock is independent), and `cumulative_factors` is the same running product;
   `adjustment_factors` (all at once) is kept and now calls them. `link_by_isin`, `add_keys`, `drop_repeated_days` are split into the steps the chunked build calls per file; their results are unchanged.
8. `universe.py`, `build_universe(..., block=, lean=)`: the rules are applied to a block of stocks at a time (each stock is judged on its own numbers plus two market-wide series,
   `vscale` and `mscale`, which are worked out once), and `lean=True` keeps the rule inputs of the last day only (`LastDay`: `inputs[name][-1, j]` and `why_not(u, j)` work as before). The defaults give the old behaviour.
   `market_scale` sums each day's row, 256 days at a time (the same sums as for the whole matrix).
9. `sectors.py`: `SectorEngine(..., lean=False)` passes `lean` on (the job sets it), and the group and page code reads `Panel.adj_col(j)` / `Panel.adj_at(t, j)` (the adjusted closes of one stock) instead of
   `Panel.adj` (a second 60 MB copy of the market). `Panel.release_pages()` gives the memory-mapped pages back.
10. `batch.py`: `run` is split into `score_stocks`, `write_sector_files` and `write_summary` (the same code, now callable on their own); `run` calls them in order.
11. `staged.py`: runs the stages (`panel`, `prepare`, `score` once per part, `merge`) each in its own process, and `finlit/sector_job.py` `default_batch` calls it (`SECTOR_PARTS`, default 4;
    `SECTOR_STAGED=0` runs the old single process). Every part builds the whole-market universe itself, so each stock is judged against the full market; the parts are split by industry group so a group is worked out once; the
    merge stage sees every group and every peer label (board order, the "too few stocks" lists, the pages).
12. `tests/big_fixture.py` (a seeded synthetic NSE folder of any size, up to the real 2,800 stocks x 10 years) and `tests/measure_job.py` (memory, time and the byte-for-byte comparison).

6. `fetch.py`, `fetch_industries`: a new listing for which NSE sends `"secInfo": null` is skipped (it used to raise AttributeError and stop the whole download after the
   prices and indices were saved: seen on the server on 4 Nov 2026). Test: `tests/test_fetch_merge.py::test_a_new_listing_whose_industry_record_is_null_is_skipped_not_fatal`.
