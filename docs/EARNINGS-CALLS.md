# Earnings-call questions (item 30)

## Design
No model training and no open chat. Ten fixed questions per company per quarter are answered by a language model that reads ONLY that company's earnings-call transcript.
Every answer is generated offline by the nightly job `refresh-earnings-calls`, checked, stored in Postgres, and served instantly and identically to every user. Cost is bounded by the job, not by visitors.

Code: `backend/finlit/earnings/` (`questions.py`, `validate.py`, `provider.py`, `transcripts.py`, `service.py`, `api.py`, `config.py`), migration `080_earnings_calls.sql`, frontend `src/stock/EarningsCall.tsx`, `src/lib/earnings.ts`, `src/styles/earnings.css`.

Tables: `earnings_calls` (one row per symbol, fiscal year, quarter; FY27 = 2027), `earnings_call_text` (extracted text, pages split by form feed), `earnings_call_answers` (answer jsonb `{covered, sentences:[{text, quote, quote_ref, source}]}`, model, prompt_version, validated), `earnings_call_usage` (keyed hash of the member, month, call id: distinct calls, so reopening is free).

## Questions
strategy-moat, guidance-outlook, margins-costs, demand-orders, capex-debt, risks-raised, management-changes, what-changed (only when the previous quarter's call is also stored), capital-allocation, analyst-concerns.

## Prompts and versions
`PROMPT_VERSION` in `questions.py` (now `v1`). One request answers all pending questions of one call. Each answer: 2 to 6 short sentences, each with ONE verbatim quote (25 to 400 characters). Bump the version when wording or rules change: calls are answered again; a validated older answer is replaced only by a new validated one.

## Validation (nothing unchecked is ever shown)
- Quote must occur in the transcript text sent (whitespace, case, curly quotes, dashes, ligatures, line-break hyphens normalised). Else the sentence is dropped.
- Advice words rejected in our sentences (buy, sell, hold, accumulate, target, recommend*, overweight, underweight, outperform, underperform; phrases such as "price target"). Quotes are not scanned.
- A question with fewer than 2 good sentences is asked once more; after that 1 is accepted; none = stored `validated=false`, retried on later nights up to 3 times per prompt version.
- "Not covered" counts only if the model said so; a missing answer is never read as not covered. Shown as "The call did not cover this."

## Cost and quotas (free tier)
Constants in `earnings/config.py`, overridable by env: 300 largest companies by market cap (`EARNINGS_TOP_COMPANIES`), latest 2 quarters (`EARNINGS_QUARTERS`), 25 calls per run, 40 PDF downloads, 120 exchange requests, 60 NSE lookups, 6 LLM requests/minute (`EARNINGS_LLM_PER_MINUTE`), 120/day (`EARNINGS_LLM_PER_DAY`, shared through Redis). 429 backs off 20/60/180 s; a daily-quota 429 stops the run. 600 calls need about 600 requests (one per call), so the first fill takes about 5 days at 120/day; after that only new calls. Widen coverage by raising the two env numbers (and the per-run constants if the quota allows).
Member limit: Gold 5 distinct calls a month (`LIMITS["gold"]["earnings_calls_per_month"]`); admins unlimited and not counted. Non-Gold: call list and question labels only, detail answers 403 `plan_required`; over the limit 403 `limit_reached` with `{used, limit}`.

## How to enable
1. Set `GEMINI_API_KEY` (and optionally `EARNINGS_LLM_MODEL` / `GEMINI_MODEL`). Without it the job prints `not_configured` and the site shows "Earnings-call summaries are not available yet".
2. Worker command `refresh-earnings-calls`; supervisor job `earnings-calls` (bulk, priority 44, NIGHT/MORNING windows, SLA 48 h, resumable, gated on the key); cron line in `deploy/crontab`.
3. New dependency `pypdf==6.21.4` (pure Python). Caddy and Vite route `/api/earnings-calls/*` to the research service.
4. Run migration 080 (automatic at start).

## Unverified (no live access offline)
- Live NSE/BSE announcement access: the NSE API shape, cookie handling, robots.txt and blocking by the exchange are untested. The stored feed (`feed_items`) is used first; NSE is fallback. Only exchange hosts are fetched.
- Gemini output quality, JSON obedience, and the default model name `gemini-3.8-flash` (copied from site-api).
- PDF text quality on real transcripts (columns, scans: scans are marked unreadable, no OCR).
- Call date is read from the announcement text when present; otherwise "Reported" falls back to the filing date.

## Owner's checklist
- [ ] Set GEMINI_API_KEY; restart worker; check `earnings-calls` in the jobs status.
- [ ] After the first night read 5 answers against their quotes in the PDF.
- [ ] Check logs for `nse_blocked` / `download_blocked`; if the exchange blocks, decide on another source.
- [ ] Decide whether the 5 calls a month limit and Gold-only are right.
- [ ] Review the wording "AI-summarised from the transcript. Check the quotes." and the advice-word list.
