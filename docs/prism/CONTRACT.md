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
| `GET /api/prism/reports/{id}/pdf` | The PDF of exactly that calculation. | `200 application/pdf` (attachment) · `410 {"status": "expired"}` once the signed snapshot (30 minutes) is gone: the page then offers to recalculate · `404` |

Limits: each member may generate 20 reports a day (refreshes count; reuse of a stored report does not); at most 2 generations
run at once across the service. `symbol` matches `^[A-Z0-9&_.\-]{1,24}$` after upper-casing; `statement` is `consolidated`
or `standalone`.

### Storage

* Postgres `prism_reports` (migration `063_prism_reports.sql`): one row per (symbol, statement) holding the newest reader view
  (`report jsonb`), `model_version`, `final`, `label`, `status`, `generated_at`. It is what `latest` and the stock page read.
* Redis `prism:snap:{id}` holds the full signed snapshot (with `snapshotReceipt`) for 30 minutes, for the PDF only.
  The snapshot never goes to the browser.

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
