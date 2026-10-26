# FinLit Prism: integration contract

**FinLit Prism** is the Gold plan's advanced financial-health rating. It is the model merged from
`Yusra-Khan532/financial-portfolio` (engine 3.6.10 plus the additive ST/LT technical assessment; see `premium-model-implementation.md`), renamed for the website.
The name is in one place on each side: `PRISM_NAME` in `backend/finlit/prism.py` and in `frontend/src/lib/prism.ts`.

A prism splits light into its bands: the rating splits a company into its four parts (Fundamentals, Valuation, Quality, Risk).
It describes a company's financial health from its filings and prices. It is never advice to buy, sell or hold anything,
and every screen and the PDF say so.

## Where things run

```
browser ──> research API (backend/finlit, port 8000) ──> site backend (site-api/backend, 127.0.0.1:8001)
            /api/prism/*  (Gold check, cache, limits)         POST /api/premium-reports (delivery inline)
                                                              POST /api/premium-reports/pdf
```

* The model, its data loading (FinEdge + Upstox, the same loader as the Stock Fundamentals dashboard) and the PDF renderer
  stay in the site backend, unchanged except where FinLit needs it (the merge is three-way against upstream 67aab4f; upstream was
  merged again up to 6ed9d2a on 26 October, see `COVERAGE.md`).
* The research API is the only door for members. It checks the plan, then calls the site backend with a short-lived
  HS256 token it signs with the shared `CMS_JWT_SECRET`: claims `{"sub": "prism:<user id>", "role": "admin",
  "iat", "exp": iat + 300}` (the same token shape as `POST /api/me/cms-token`). The site backend's existing
  `require_admin` accepts it; members never see that token.
* The site backend's own `/api/premium-reports*` routes stay administrator-only (CMS token) as upstream.

## Research API: `/api/prism/*`

All answers carry `Cache-Control: no-store`. Plan check: Gold or administrator (`role == "admin"`); the showcase symbols
(`settings.showcase_symbols`) are open to everyone, as on the rest of the site. Refusals use the site's usual shape
`{"status": "...", "detail": "...", "plan": "gold"}`.

| Method and path | Purpose | Answers |
| --- | --- | --- |
| `GET /api/prism/status` | Is Prism connected? Public. | `200 {"name": "FinLit Prism", "available": bool, "reason": str \| null, "modelVersion": str \| null}` |
| `GET /api/prism/reports/latest?symbol=TCS&statement=consolidated` | The newest stored report for a company, without generating. | `200 PrismReport` · `404 {"status": "none"}` · `403 plan_required` |
| `POST /api/prism/reports` body `{"symbol": "TCS", "statement": "consolidated", "refresh": false}` | Generate (or reuse a report under 6 hours old unless `refresh`). | `200 PrismReport` · `403 plan_required` · `404 not_found` · `422 bad_request` · `429 limit` (with `Retry-After`) · `502/503 unavailable` |
| `POST /api/prism/reports` with `"background": true` | Same checks and limits, but answers at once: `200 PrismReport` when a stored report is fresh, else `202 {"status": "working", "startedAt", "elapsedSeconds", "expectedSeconds", "pollSeconds"}` while a calculation runs (started by this request, or already running for another member: it is joined, not repeated). | `202` · `429 limit` |
| `GET /api/prism/jobs?symbol=TCS&statement=consolidated` | Where that calculation is. Same plan rule as `latest`. | `200 {"state": "working", "elapsedSeconds", "expectedSeconds", "pollSeconds"}` · `{"state": "ready"}` (read `latest`) · `{"state": "failed", "status", "code", "detail", "retry"}` · `{"state": "none"}`. A job whose process died is reported `failed` after 3 minutes, never `working` for ever. |
| `GET /api/prism/reports/{id}/pdf` | The PDF of exactly that calculation. | `200 application/pdf` (attachment) · `410 {"status": "expired"}` once the signed snapshot (30 minutes) is gone: the page then offers to recalculate · `404` |

Limits: each member may generate 20 reports a day (refreshes count; reuse of a stored report does not); at most 2 generations
run at once across the service. `symbol` matches `^[A-Z0-9&_.\-]{1,24}$` after upper-casing; `statement` is `consolidated`
or `standalone`.

### Storage

* Postgres `prism_reports` (migration `063_prism_reports.sql`): one row per (symbol, statement) holding the newest reader view
  (`report jsonb`), `model_version`, `final`, `label`, `status`, `generated_at`. It is what `latest` and the stock page read.
* Redis `prism:snap:{id}` holds the full signed snapshot (with `snapshotReceipt`) for 30 minutes, for the PDF only.
  The snapshot never goes to the browser.
* Postgres `prism_inputs` (migration `064_prism_inputs.sql`): the packed model inputs of a company's last interactive calculation,
  reused for 24 hours (15 minutes for "Recalculate"), rows older than 2 days deleted on write. Redis `prism:obs:{statement}:{date}` (4-5 days)
  holds the one price-ratio row per industry peer that the medians used, shared by every company of that industry; `prism:univ:*` the peer
  list of a company; `prism:job:*` the state of a background calculation; `prism:durations` how long recent from-scratch calculations took.
  None of this changes a number: the site backend receives them as `inputs` / `observations` on `POST /api/premium-reports` and the model is fed the same data.

### `PrismReport` (what the browser receives)

The site backend's ready snapshot **minus** `calculationTrace`, `inputs`, `inputHash`, `snapshotReceipt` and
`snapshotExpiresAt`, **plus**:

```ts
{
  id: string;                 // the calculation id (32 hex)
  createdAt: string; completedAt: string; statementType: "consolidated" | "standalone";
  company: { symbol: string; name: string; industry?: string | null; sector?: string | null; description?: string | null };
  rating: {                   // premium_engine.score_company output, unchanged
    modelVersion: string; baselineVersion: string; fillVersion: string; group: string;
    final: number | null; label: "STRONG" | "HEALTHY" | "AVERAGE" | "WEAK" | "POOR" | "NOT RATED";
    status: "RATED" | "PROVISIONAL" | "NOT RATED"; parts: Record<"fundamental" | "valuation" | "quality" | "risk", number | null>;
    partWeights: Record<string, number>; coverage: Record<string, number>; confidence: number; judgedQuarters: number;
    dataIntegrityStatus: "PASS" | "REVIEW REQUIRED"; metrics: Metric[]; loss: unknown; ...
  };
  inputMeta: Record<string, unknown>; warnings: string[]; sources: unknown[]; trends: { period: string; revenue: number | null; profit: number | null; eps: number | null }[];
  benchmark: Record<string, unknown>; review: Review;          // premium_presentation.build_report_review
  technicalAssessment?: TechnicalAssessment;   // engine 3.6.10 and later; absent on reports made before it (see the next section)
  cached: boolean;            // true when served from storage instead of a fresh calculation
  pdfAvailableUntil: string | null;   // ISO time the PDF stays downloadable, null once expired
}
```

### `technicalAssessment` (what the browser receives)

The additive ST/LT market assessment of `premium-st-lt-model.md` ("Report contract"). It is **separate** from the financial-health
`rating` (it is not in `rating.parts` and does not change `rating.final`); the stored report and the PDF carry it as they carry the
rest. The research API (`prism.reader_view` / `prism.technical_view`) copies it from the signed snapshot through an **allow-list**:
`inputHash`, `sourceCodeSha256`, every factor's internal `weight` and anything that is not a plain value (a raw candle or index
series) are not passed on; scores, ratings, signals, labels and notes are copied exactly. A report made before 3.6.10 has no
`technicalAssessment` key at all: show nothing, and offer to recalculate. `status: "incomplete"` is normal when provider history
is missing: scores are `null` and the factors say what is missing.

```ts
type Part = {                      // shortTerm and longTerm
  score: number | null;            // -100 to +100, full precision (round for display only); null until every enabled factor is available
  rating: "Strong Buy" | "Buy" | "Hold" | "Reduce" | "Sell" | "Unavailable";   // the model's own words; the website relabels them
  status: "ready" | "incomplete";
  horizon: string;                 // "5–20 sessions" | "6–18 months"
  availableCount: number; requiredCount: number;   // ST 14 and LT 13 with the supplied defaults
  stageCapped: boolean;            // long term only in effect: market stage 3 or 4 limited the score to +19
  factors: { key: string; label: string; signal: number | null;   // -1 to +1
             status: "available" | "unavailable" | "disabled";
             detail: string }[];   // reader text for an available factor, the reason for an unavailable one (this is the model's `detail`)
};
type TechnicalAssessment = {
  modelVersion: string;            // e.g. "st-lt-14.3"
  status: "ready" | "incomplete";  // ready only when both scores exist
  asOf: string | null;             // date of the latest daily close used (YYYY-MM-DD)
  provider: string;                // "Dhan" | "FinEdge" | "Upstox" | "Unavailable"
  dailyBars: number; usableDailyBars: number; fresh: boolean;   // fresh: latest close is at most 10 days old
  shortTerm: Part; longTerm: Part;
  verdict: { label: string; tone: "positive" | "caution" | "negative" | "muted" };   // the model's own wording, e.g. "ACCUMULATE ON DIPS", "Unavailable"
  notes: string[];                 // data-source and limitation notes, to be shown
  observations: Record<string, string | number | boolean | null | string[]>;   // stage, freshStage2, slope150Pct, benchmark, benchmarksUsed, beta, rsRatingST, rsRatingLT
  benchmarkSources: Record<string, { provider: string | null; asOf: string | null; bars: number }>;   // per index; `bars` is a count
  options: { sectorRS: boolean; valueMigration: boolean };
};
```

Trimmed example (engine 3.6.10, synthetic prices, from `backend/tests/fixtures/prism/snapshot_example.json`):

```json
"technicalAssessment": {
  "modelVersion": "st-lt-14.3", "status": "ready", "asOf": "2026-10-16", "provider": "FinEdge",
  "dailyBars": 700, "usableDailyBars": 700, "fresh": true,
  "shortTerm": {"score": -14.84375, "rating": "Hold", "status": "ready", "horizon": "5–20 sessions", "availableCount": 14, "requiredCount": 14, "stageCapped": false,
    "factors": [{"key": "ema_stack", "label": "EMA alignment", "signal": 0.0, "status": "available", "detail": "EMA 9 / 20 / 50: 234.15 / 234.41 / 231.00; ADX 29.5."}]},
  "longTerm": {"score": 39.130434782608695, "rating": "Buy", "status": "ready", "horizon": "6–18 months", "availableCount": 13, "requiredCount": 13, "stageCapped": false,
    "factors": [{"key": "stage", "label": "Market stage", "signal": 0.5, "status": "available", "detail": "Stage 2: established advance."}]},
  "verdict": {"label": "ACCUMULATE ON DIPS", "tone": "positive"},
  "notes": ["Scores use the latest completed daily session; weekly signals use the preceding week."],
  "observations": {"stage": 2, "freshStage2": false, "slope150Pct": 5.448, "benchmark": "Nifty Smallcap 100", "benchmarksUsed": ["Nifty Smallcap 100"], "beta": 0.3, "rsRatingST": 43.65, "rsRatingLT": 12.30},
  "benchmarkSources": {"Nifty 50": {"provider": "FinEdge", "asOf": "2026-10-16", "bars": 700}},
  "options": {"sectorRS": false, "valueMigration": true}
}
```

Wording and compliance: `rating` and `verdict.label` are upstream model words (Strong Buy, Buy, Reduce, Sell, "SELL / AVOID" and so on). The research API
passes them through unchanged and adds no wording of its own; the website's display layer relabels them, and the "not a recommendation"
line stays on every screen and the PDF. The PDF is rendered by the site backend from the full signed snapshot (weights included in
the document, none printed), so it never depends on the reader view.

The exact rating, metric and review shapes are the upstream ones: read `site-api/backend/premium_engine.py`,
`premium_presentation.py`, `premium_completeness.py` and the upstream page `PremiumReportPage.jsx`
(`/home/user/yusra-khan532/financial-portfolio/frontend/src/pages/PremiumReportPage.jsx`) before typing them.

## Website

* `/prism` — company search and the latest reports a member opened; `/prism/:symbol` — the report (generate, recalculate,
  PDF). Gold, behind the usual `Gate` for others (with a preview of what it shows).
* Stock page — a Gold card in the hero's report area or its own section: the Prism label and score if a stored report
  exists, else a "Generate the Prism rating" button; it links to `/prism/:symbol`.
* Navigation (`frontend/src/lib/nav.ts`), the Gold hub, the Plans page and the home page name it.
* Wording: never "buy", "sell", "avoid", "target"; always "Describes the company's financial health from its filings and
  prices; not a recommendation." Status is given in words, never by colour alone.

## Stock page: side-by-side comparison (owner requirement, 25 Oct)

On every company page, for **Gold** members, the first dashboard (the report block under the company name with the overall score and the pillar scores: Quality, Growth, Profitability, Balance, Technical) becomes a **two-column comparison**:

* **Left half: "FinLit score" (the basic model, unchanged):** exactly what is shown today (overall score, pillar bars, thesis, strengths/watch-outs).
* **Right half: "FinLit Prism" (the advanced model):** the Prism score out of 100, label (STRONG … POOR / NOT RATED) and status (RATED / PROVISIONAL / NOT RATED) in words, confidence ("x% of inputs available"), and the four parts (Fundamental, Valuation, Quality, Risk) as bars styled like the left side's pillar bars, so the two can be compared at a glance. Below: the top two pros and cons from `review`, the data date, a "Recalculate" action and a link "Open the full Prism report" (`/prism/:symbol`).
* The technical side arrived as the separate `technicalAssessment` (see its section above), not as a `rating.parts.technical` part: show its short-term and long-term scores from `technicalAssessment` when present. A `technical` part in `rating.parts` still renders automatically if `partWeights` ever lists it. For reports without `technicalAssessment` show a quiet, honest "not calculated for this report; recalculate" row. Never invent a number.
* If no stored Prism report exists for the company: right half shows a calm explanation and a **Generate the Prism rating** button (generation usually takes under half a minute; show progress; the **stock page** never generates by itself, but the **Prism page** `/prism/:symbol` does start one in the background when it opens a company that has no rating, shows a determinate-looking progress bar with the real elapsed seconds, polls `/api/prism/jobs` with a growing pause (1 s to 5 s) and shows the report when it is stored; a failure or a calculation over about 3 minutes ends as a message with a Retry button, never a stuck spinner). While loading the stored report show a skeleton of the same size (no layout jump).
* Non-Gold members keep the single-column report they have today; the right half is replaced by a short locked teaser (`Gate`), so the comparison is visibly something Gold adds. Showcase symbols are open to everyone.
* Phone (≤ 760 px): the halves stack, FinLit score first, then Prism, each with a clear heading. Both halves use the same visual grammar (ring, bars, status words) so differences in numbers, not styling, are what the eye sees. No colour-only meaning; aria-labels state each conclusion. Compliance line under the block.
* The rest of the stock page is adapted to the advanced model where it explains scores: the "Pros & cons" (method) section and notes show a Prism sub-section for Gold when a report exists (its `review` pros/cons per part and the completeness list), the section nav links to it, and the downloads menu offers the Prism PDF when a report exists.
