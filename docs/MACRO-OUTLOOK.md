# Macro & Sector Outlook

Spec: `docs/macro-sector-outlook-prd.pdf` (text copy `.txt`). Code: `backend/finlit/macro_outlook/` (engine, seed, store, views, api), migration `088_macro_outlook.sql`, job `macro-outlook` (`refresh-macro-outlook`), company-page section `frontend/src/stock/MacroOutlook.tsx`, admin `frontend/src/components/admin/MacroAdmin.tsx` (Console > Macro outlook).

## Architecture
stored series (`macro_points`, `macro_meta`, `commodity_snapshots`; filled by the existing macro, flows and commodity jobs) -> `macro_indicator_history` (every observation and revision, with unit, observation date, publication date and its basis, source, retrieval time) -> `macro_indicators` (current reading + status) -> signals (Level + Momentum, each capped at +-1, averaged) -> sector sensitivity matrix (database, versioned) -> sector score -> immutable snapshot (`sector_macro_scores` + `sector_macro_contributions`, update/delete blocked by trigger) -> Redis -> company page. The company page and every public route read stored snapshots only; none calls an external source.

Formula (fixed, versioned, in `engine.py`): Contribution = Signal x Sensitivity x Weight; WeightedSignal = SignalScale x sum(contributions of valid indicators) / sum(weights of valid indicators); Score = 50 + 50 x tanh(WeightedSignal / K). Coverage = valid weight / total weight; below 70% or with a critical indicator not valid the result is Insufficient Data (no score, nothing zero- or neutral-filled). Bands 80-100 Strong Tailwind, 65-79 Tailwind, 45-64 Neutral, 25-44 Headwind, 0-24 Strong Headwind (label from the whole-number score shown). Top two drivers by absolute contribution, ties by configured priority, then fresher observation, then code.

**Decision to confirm: SignalScale = 5.** With weights normalised as the PRD recommends, the weighted signal lies in [-1, +1], so the PRD's trial K = 3 (meant for an unnormalised sum) would squeeze every score into 34-66 and make Strong Tailwind/Headwind unreachable. The model therefore carries `signal_scale` (5) with K = 3. Both are configuration, stored per model version and in every snapshot. Not validated.

Signal convention: positive = indicator high or rising, negative = low or falling; the sector coefficient (+1 helps, -1 hurts) decides the effect. Level methods: threshold, hump (overheating credit growth is not better than healthy), pct_vs_mean, percentile, zscore; momentum: change or pct_change over a lookback. If no earlier reading exists the level alone is used and the page says so.

Look-ahead: `known_series(as_of)` uses only rows with publication date <= as-of, latest revision published by then. A revised value is a new revision with publication date = first retrieval; earlier snapshots keep the original.

Publication dates: where the release date is not recorded it is the observation date (`pub_date_basis = assumed_observation_date`); newly seen observations get the first-retrieval date (`first_seen`); repo series `derived_from_announcements`; daily FX/commodities `same_day`; RBI credit/deposits use the press release date when readable. History before the first live run is **reconstructed** (month-end, labelled) and can include figures slightly before release.

Stale: an indicator older than its limit is Stale and excluded. A snapshot older than `stale_after_hours` (48) or after a failed run is served with a visible stale warning, never as current.

## Indicator data availability (stored data today)
| Indicator | Covered | Freshness | Source |
|---|---|---|---|
| CPI, Food CPI | yes (monthly) | released ~12th for previous month; stale after 100 days | MoSPI (`refresh-macro`) |
| WPI | yes | as above | MoSPI |
| GDP growth | yes (quarterly) | stale after 200 days | NSO / MoSPI |
| IIP, capital / infra / durables / non-durables | yes | stale after 100 days | MoSPI |
| Unemployment | yes (PLFS monthly from 2025) | 100 days | MoSPI PLFS |
| Repo rate, 12-month policy change | yes | on RBI announcement | RBI (current rates + decision history) |
| Bank credit, deposit growth | yes, but history only from the first read of RBI's weekly statement | 45 days | RBI WSS |
| USD/INR | yes (monthly averages, daily FBIL) | 10 days | RBI / FBIL |
| Brent, copper, aluminium, natural gas | **only if a commodity vendor key is set** (`METALS_DEV_API_KEY`, `METALPRICE_API_KEY`); otherwise Missing with that reason | 10 days | metals.dev / MetalpriceAPI via the commodity worker |
Not in the model (no source yet): global demand, steel, coal, cotton, sugar prices, passenger traffic, auto sales, asset quality. IT services therefore rests on rupee, GDP, CPI and unemployment only.

## What the engine produces on the seed data (recorded fixtures)
Without commodity keys 20 of 35 sectors score (for example Capital goods 75, PSU banks 75, Private banks 74, Consumer durables 67, FMCG 29 Headwind) and 15 show Insufficient Data because a critical commodity input is missing (aviation, oil marketing, upstream, paints, fertilisers and others) or coverage is below 70%. With a Brent key most of them score.

## Company mapping
`macro_label_map` holds reviewable rules from exchange Sector / Industry labels (exact first, then wording rules), named symbols (PSU banks) and revenue-segment words. A company gets a primary mapping with an effective date, or a row in `company_macro_unmapped` with the reason (no label yet, or no rule matches). Administrator mappings are never overwritten. Diversified companies are revenue-weighted only when reported segment revenue maps at least 80% to covered sectors (weights normalised over the mapped part, rule recorded); otherwise the primary sector is used and the page says so. No weights are invented.

## Admin
`/api/admin/macro/*` (admin role + MFA, Origin and CSRF like other admin writes): overview and data health, sensitivities, `POST sector-sensitivity`, `config` (K, scale, coverage, bands, indicator settings), mapping, label rules, contributions, audit, activate-version (rollback), recalculate. Every change creates a new model version (copy, edit, activate), writes old and new values with user and time to `macro_audit_log`, and recalculates; old versions and snapshots are untouched.

## Plan gating
Free for everyone: `auth/entitlements.py` has no macro entry. The earlier Gold-only, flag-gated preview (`/api/macro/sectors`, `macro_sectors` flag) is superseded on the company page (its Hero line is removed so two different numbers never appear); it remains on the Macro page and should be switched to the new engine or removed (open item).

## Founder decisions
Sector mapping rules, the seeded sensitivities and critical flags (all initial assumptions), K and signal scale, 70% coverage, whether reconstructed history is shown, what to do with the old Macro page panel, and which commodity vendor keys to set on the server.
