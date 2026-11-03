# Prebuilt screens (Advanced and Basic score screeners; spec "Prebuilt Screens Spec", 31 Oct 2026, rebuilt per the "Pre-built Filter Redesign", Nov 2026)

Code: `backend/finlit/presets/` (registry, engine, derive, themes, industry, seed, service, api). Migration `078_presets.sql`. Tests: `tests/test_presets.py`, `tests/test_presets_api.py`.
Gold only (same gate as the Prism columns of the screener; admins too). Below Gold the list has names and card text only (`count` null, `locked` true) and the detail/export answer 403 `plan_required`.

## Redesign (registry version 2)
* **Two tabs, one registry.** `Preset.tab` is `advanced` (Gold, Prism fields) or `basic` (Silver, FinLit score fields). `GET /api/screener/presets?tab=basic` lists the Basic cards; the detail/export gate follows the screen's own tab (`plan_required` names Gold or Silver). A rule uses only fields the tab shows, plus the 52-week high/low and 3-, 6-, 12-month returns.
* **Top 10 Large / Mid / Small** (`highest-rated-*` on Advanced, `basic-top-*` on Basic): gates (Advanced: Rated only, Prism 60+, Quality 50+, Risk 50+/60+ small, long-term view above -20, within 30% of the 52-week high; Basic: Growth & Profitability 65+, Technical 45+, Quality 50+, Balance sheet 45+/55+ small with a blank allowed for banks, within 30%, Rs 1,000 Cr+) then a weighted percentile rank score (`Preset.rank_score`, 100 x sum of weight x percentile among the size bucket's members: Advanced = Rated Prism companies, Basic = Rs 1,000 Cr+), at most 3 per Sector label (`sector_cap`), ties by Quality then Prism (Advanced) or Growth & Profitability then FinLit IQ (Basic). A short Advanced list is filled with names failing only the trend or 52-week gate, badged "Trend not confirmed" (`fill`). Cards say "Top 10 of N that pass" (`listText`).
* **Themes.** `theme_map.py` replaces the hand-made list: sub-themes found from the Sector label plus a short named list the research team reviews each quarter (Defence, aerospace and shipbuilding is new). `themes.py` breadth = share of a sector's Rs 1,000 Cr+ stocks within 15% of their 52-week high (response fields `breadth`, `marketBreadth`).
* **Moved.** Results-season standouts, Steady dividend payers and Institutions buying are Stock screener ready-made screens (`frontend/src/lib/proscreen.ts`, `READY`). Rating upgrades and PSU stocks stay blocked with a plain-words reason.
* **Optional columns.** Both score screeners can add 3M/6M/1Y return and Below 52-week high (`store.PRICE_EXTRAS` reads them from `scores.metrics`; `components/screener/PriceColumns.tsx`).

## API
* `GET /api/screener/presets` -> `{asOf, groups:[{id,name,presets:[{id,name,group,cardText,count,asOf,status,blockedReason,chips,howItWorks,locked,...}]}]}`
* `GET /api/screener/presets/{id}?chip=a&chip=b` -> `{id,name,asOf,count,shown,columns,rows,chips,howItWorks,cardText,disclaimer, themes?, closestMisses?}`.
  No `chip` parameter = the chips that are on by default; `chip=none` = no chips; the response echoes the active ids in `chips`. Unknown id 404, unknown chip 422, blocked screen 409 (`blockedReason`), cache still empty and another worker computing 503 `computing`.
* `GET /api/screener/presets/{id}/export?chip=...` CSV with the screen's columns (up to 500 rows, BOM, disclaimer line). Gold (the data is Gold; the existing table export stays Silver).
* Extra fields: `ratedCount`, `of` (F&O stocks / rated small caps), `emptyText`, `market`, per-theme `b200`, `marketB50`, `small`, `reason`.

## Registry (`registry.py`)
One `Preset` record per screen: `id, name, group, card_text, prism_filters (zmin zfmin zvmin zqmin zrmin st lt rated status cap), ql (Query-builder lines), derived ((rule,label)), rank, limit, columns, chips, how_it_works`. `REGISTRY_VERSION` is part of every cache key: bump on any rule change.
Rules run through the Query builder's own parser/evaluator (`screener/ql.py`, `qeval.py`), so a missing figure fails exactly as there. `derived` uses the tiny language in `expr.py` (`coalesce`, `bankzero`).
Groups: Top rated, Trend, Growth, Themes, Value and income, Safety, Ownership, Prism basics (the page's 4 quick views, listed, `handledBy: frontend`, no server detail).
Missing-value rules: screens 1-3 count a missing red-flag count as 0; screens 5, 6, 13 do so for banks/lenders only; screen 5 exempts banks from ROCE and D/E.

## Nightly job `refresh-presets` (worker command; supervisor job `presets`: bulk, priority 42, after `prism`, NIGHT 20 h / MORNING 14 h windows, SLA 30 h; backend/finlit/jobs/registry.py 06:40)
Tops up `theme_tags` from `seed.py`, rebuilds `industry_clean`, stores `preset_scores` (momentum, growth), `industry_breadth_daily` (60 sessions; `*` = market), outlier caps (`preset_meta`), then every live screen for its default chip set and each single chip into `preset_results` (Postgres) and Redis (36 h). API only reads; an empty cache is computed on demand behind a Redis lock (45 s bound).
Percentile = average rank among stocks of Rs 1,000 Cr or more, scaled 0..1. Growth score needs 2 of 4 numbers (quarter numbers drop out under Rs 50 Cr sales).
Sector themes: universe Rs 500 Cr+, cleaned industry, generic industries excluded, groups of 8+ are themes, 5-7 are "small groups" (chip), states In play / Emerging / Fading / None as spec p10; Emerging/Fading appear only once 20 sessions are stored (no backfill is invented). Never-empty rule shows up to 3 "closest".
Usage: `preset_usage(day, preset_id, event open|export, plan, n)`: counts only, no user id or IP.

## Data fixes: done / not done
Done: cleaned industry (trim, case, merge variants incl. Oil/Gas and Media-Publication, strays DVR/Engineering to none) as derived `industry_clean`; raw data untouched; theme_tags + seed; breadth job; outlier caps; market-cap floor in place of volume.
Not done: moving companies off generic industries (needs NSE industry; fill `industry_override`); average-volume fix (CRISIL) and the Rs 2 Cr traded-value floor; `is_psu` and Prism history (screens PSU stocks and Rating upgrades are exposed as `blocked`); companies without market cap; Prism coverage; mapping SIFY, SPEL, ASMTEC, CEINFO (listed as pending in the seed, loaded the night they appear in `companies`; Amara Raja's old symbol AMARAJABAT is an alias of ARE&M).

## How to add a screen
1. Add a `Preset` to `PRESETS` in `registry.py` (use Query-builder lines first, `derived` only when a nightly field or Prism part is needed; new nightly fields go in `derive.py` and `Frame.get`).
2. Bump `REGISTRY_VERSION`. 3. Add pass and fail cases per rule in `tests/test_presets.py`. 4. Run `refresh-presets`; the card appears in its group.
