# Company brief (issue 44)

The About section of each company page, written from the company's own filings, every line cited, shown only after a person publishes it.

- Code: `backend/finlit/company_brief/` (core.py pure logic, service.py nightly job, api.py routes), migration `091_company_brief.sql`, `frontend/src/stock/CompanyBrief.tsx`, Console tab "Company brief" (`components/admin/BriefAdmin.tsx`).
- Job `company-brief` (`refresh-company-brief`): needs `GEMINI_API_KEY` (the Ask FinLit AI key; optional `BRIEF_LLM_MODEL`). No key = recorded "not configured", nothing written. Knobs: `BRIEF_MAX_WRITES_PER_NIGHT` (6), `BRIEF_LLM_PER_MINUTE` (4), `BRIEF_LLM_PER_DAY` (60), `BRIEF_TOP_COMPANIES` (500).
- Order: rewrite asked, followed companies (opened in 90 days or active alert), then market cap. Only companies with new filings are rewritten, and only the parts `refresh_plan` names.
- Gates: validate() blocks advice words (buy, sell, reduce, avoid, accumulate, price target, top pick, multibagger...); hold/target/best are flagged for the reviewer, never blocking (they are fine as the company's own words). check() needs every cited string on its cited PDF page. A failed brief is stored as a draft that cannot be published.
- Annual report address is not in the feed: set per company in the Console (`company_brief_sources.annual_report_url`), else the newest "Annual Report" announcement in feed_items is used. OPEN: bulk-fill addresses.
- Public: `GET /api/stocks/{symbol}/brief` (published copy only, re-validated on every read, otherwise a reasoned empty state). Admin: `/api/admin/company-brief/*`.
- The Reliance prototype lives only in `backend/tests/fixtures/company_brief/` and `frontend/src/lib/fixtures/`; never loaded into production.
