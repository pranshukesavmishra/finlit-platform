# FinLit Prism: integration contract

**FinLit Prism** is the Gold plan's advanced financial-health rating. It is the model merged from
`Yusra-Khan532/financial-portfolio` (engine 3.6.9; see `premium-model-implementation.md`), renamed for the website.
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
  stay in the site backend, unchanged except where FinLit needs it (the merge is three-way against upstream 67aab4f).
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
  cached: boolean;            // true when served from storage instead of a fresh calculation
  pdfAvailableUntil: string | null;   // ISO time the PDF stays downloadable, null once expired
}
```

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
* Prism has **no technical part yet** (it is being built and arrives in 1-2 days). Render the parts from the data: a `technical` part appears automatically when `rating.parts.technical` is present and `partWeights` lists it. Until then show a quiet, honest placeholder row "Technical: coming soon" in the right column. Never invent a number.
* If no stored Prism report exists for the company: right half shows a calm explanation and a **Generate the Prism rating** button (generation usually takes under half a minute; show progress; the **stock page** never generates by itself, but the **Prism page** `/prism/:symbol` does start one in the background when it opens a company that has no rating, shows a determinate-looking progress bar with the real elapsed seconds, polls `/api/prism/jobs` with a growing pause (1 s to 5 s) and shows the report when it is stored; a failure or a calculation over about 3 minutes ends as a message with a Retry button, never a stuck spinner). While loading the stored report show a skeleton of the same size (no layout jump).
* Non-Gold members keep the single-column report they have today; the right half is replaced by a short locked teaser (`Gate`), so the comparison is visibly something Gold adds. Showcase symbols are open to everyone.
* Phone (≤ 760 px): the halves stack, FinLit score first, then Prism, each with a clear heading. Both halves use the same visual grammar (ring, bars, status words) so differences in numbers, not styling, are what the eye sees. No colour-only meaning; aria-labels state each conclusion. Compliance line under the block.
* The rest of the stock page is adapted to the advanced model where it explains scores: the "Pros & cons" (method) section and notes show a Prism sub-section for Gold when a report exists (its `review` pros/cons per part and the completeness list), the section nav links to it, and the downloads menu offers the Prism PDF when a report exists.
