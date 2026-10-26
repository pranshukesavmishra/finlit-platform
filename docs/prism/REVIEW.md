# FinLit Prism: adversarial review

Reviewed at integrated branch head 5430221 (`claude/prism-model`); fixes are commits b8bd6a1 (research API) and 85d089b (website).
Evidence was read from code and run locally: research API `tests/test_prism.py` 36 passed, site backend 450 passed / 1 skipped, website vitest 706 passed.
Not done here (A5 covers end to end): real-provider runs, live stack browser runs.

## Critical
None.

## High

**H1. The stock page card showed category scores for a company the model did not rate.** `frontend/src/stock/PrismCompare.tsx` `partsOf` / `Tiles`.
The engine returns `rating.parts` even when `status` is `NOT RATED` (see `prismVariants.json` `notRated`: 58.2, 16.5, 64, 67). The full page hides them; the stock card drew a ring, a number, a word ("Poor") and a bar per part, contradicting its own text "no score" and CONTRACT. Evidence: rendering the card with the `notRated` fixture gave aria-labels "Fundamentals: 58 out of 100, average ...". Fixed in 85d089b (parts null when NOT RATED; test in `PrismCard.test.tsx`; mutation check fails the test). The summary endpoint now also withholds `parts` for NOT RATED (b8bd6a1, `test_not_rated_summary_withholds_category_scores`).

## Medium

**M1. Any signed-in free member could force recalculations of showcase companies.** `prism.py` `create`: `refresh` was honoured for every authenticated user, so Basic accounts could burn 20 paid-provider calculations a day each and replace the shared stored row. Fixed in b8bd6a1: refresh needs Gold or administrator (403 `plan_required`); test `test_only_gold_and_administrators_may_force_a_recalculation`.

**M2. PDF endpoint had no rate limit** although showcase PDFs are open to visitors and every download is rendered by the site backend. Fixed in b8bd6a1: 30 per 10 minutes per member or visitor address (`PDF_LIMIT`, 429 `limit`); test added.

**M3. Research API allows 2 calculations at once, the site backend 1 on Render** (`PREMIUM_GENERATION_SLOTS=1`). The second request queues in the site backend, its 170 s read timeout expires, the member sees a failure and the site keeps computing in vain. Fixed in b8bd6a1: `PRISM_SLOTS` (default 2, 1 to 4), `render.yaml` sets 1 so the second request gets a quick "busy". CONTRACT says "across the service"; the limit is per process (the deploy runs one worker).

**M4. Stock card and Prism page used different query keys**, so a rating generated on one page showed "No Prism rating yet" on the other for up to 60 s. Fixed in 85d089b (each success invalidates the other key). Not covered by a unit test (needs a two-page flow).

## Low

* L1. 429 `busy` (all slots taken) was shown as "Calculation limit reached" with no retry button. Fixed 85d089b (`prismProblem`, test).
* L2. `REPORT_ID` used `$`, which also matches before a trailing newline (`/reports/<id>%0A/pdf` passed validation; harmless 404 afterwards). Fixed b8bd6a1 with `\Z`, in the PDF test.
* L3. Reports are stored under the typed symbol, not the resolved company: the site backend resolves ISINs and BSE codes (rank 0 match), so typing `INE467B01029` stores a TCS report under another key, invisible to the stock page and growing the table. The plan check uses the typed symbol, so no gating bypass was found (a showcase symbol resolves to itself by exact match). Not fixed: aliases such as TATAMOTORS to TMPV make a blind equality check wrong. Suggest rejecting codes that are not ticker symbols.
* L4. Visitor limit key uses the raw address; the site's limiter groups IPv6 by /64, so a visitor with a /64 can rotate addresses. Not fixed (needs a private helper exported).
* L5. Waiting requests (`_wait_for`) are uncapped: many visitors on a stale showcase report each hold a task up to 200 s. A `prism:fail` answer (30 s) can be handed to a later waiter after an unrelated "busy" end. Not fixed.
* L6. Light theme contrast: `--pz-*` tokens are 4.8 to 6.9:1 on `--s1` but 4.16 to 4.40:1 on `--s2` (strong, healthy, average, weak) and the small `.pz-kind` chip is about 4.3:1. Status is always in words and shapes, never colour alone. Not fixed.
* L7. `GET /api/prism/status` is public and reveals `not_reachable` and the model version (no secrets).
* L8. A rejected client refresh for a Basic member now shows the generic "part of Gold" text.

## Info

* Migrations: this branch adds only `063_prism_reports.sql`; 060 to 062 are on `claude/leadership-followups` (PR 69), and the runner records versions by file name, so 063 is the next free number once 059 to 062 are on main. SQL is idempotent (`IF NOT EXISTS`, conditional GRANT) and indexed on `id` and `generated_at`.
* Model fidelity: all 12 model files (`premium_*.py`, `fundamental_resolution.py`, `financial_fields.py`, `benchmark_resolution.py`) are byte-identical to upstream (`cmp`). Upstream's tests (including those 22 premium tests) run unchanged in the 450 site tests. Only 4 upstream test files differ, by added tests.
* Coverage ledger: 256 of 256 upstream files are listed; all 60 `merged-identical` rows verified with `cmp`. For `server.py`, a plain diff against upstream shows exactly the intentional FinLit differences (optional MongoDB, portfolio and upload copies in MongoDB, `CMS_PASSWORD_LOGIN`, chat plain text, no `*.vercel.app`, bounded cache, slots setting, enquiry list). The one upstream line absent (`point_key = ...`) is an unused assignment already absent on main. No duplicate top-level definitions.
* Token: HS256, claims `sub` `prism:<user id>` / `prism:visitor`, `role` admin, 300 s; only `prism.py` and `premium.py` mint it, with a 32-byte secret check on both sides. Members never see it; the proxy cannot supply one. The catch-all forwards `/api/premium-reports*` but the site backend requires an admin token there (tested). Site backend without MongoDB: every database route raises a 503; no route skips `require_admin`; the password-only CMS login is off by default (new, stricter than upstream). `_resolve_finedge_stock` only passes resolved symbols to provider paths (quoted), so no path injection.
* Daily limit uses atomic INCR then compare (no check-then-increment race); lock release compares a token; CSRF and Origin are enforced for signed-in POSTs like `auth/routes.py`, visitors get the Origin check only.
* Contract leakage: the reader view drops `calculationTrace`, `inputs`, `inputHash`, `snapshotReceipt`, `snapshotExpiresAt`; scanning it for tokens, URLs, keys and equations found nothing. `sources` hold provider names and dates only. `inputMeta` and `benchmark` (including provider benchmark observations) are passed as upstream builds them.
* Wording: no buy/sell/avoid/target/recommend language in new strings, in the review text or the PDF; the compliance line is on the report, the stock card, the hub card and the glossary. PDF metadata title still says "FinLit Premium Report" (upstream).
* Frontend crash test (every key removed or nulled in the real fixtures): crashes only for keys the engine always sends; reports without `review`, `financialHistory`, `benchmark.metrics`, `loss`, or with NOT RATED and PROVISIONAL, render. Unfinished contract items: the stock page section nav does not link to Prism (only the hero tag does); the stock page loads the full report, so `view=summary` is unused.
* CI: `bandit -r backend/finlit -ll` clean; site-api (not in CI scope) has two Low findings (B406 `escape` import, B112). `pip-audit` could not be run here. `site-api/backend/requirements.txt` ships pytest and xdist (upstream).
* Mutation checks (break code, test fails, restore): refresh gate, PDF limit, NOT RATED summary, CSRF call, daily limit, stock card NOT RATED parts: all failed as they should.
