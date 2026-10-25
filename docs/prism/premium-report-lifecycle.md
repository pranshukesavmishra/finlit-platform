# Premium report lifecycle and deployment

For financial sourcing, formulas and applicability rules, read the [implementation guide](premium-model-implementation.md). For payloads and normalized fields, read the [input/output contract](premium-model-input-output.md).

## Current generation flow

1. The administrator selects an exact company and statement basis. The frontend posts to `/api/premium-reports` with `delivery: "inline"`.
2. The backend resolves identity, loads the same financial observations as Stock Fundamentals, applies shared recovery and benchmarks, then computes one deterministic rating and its trace/review.
3. Generation finishes in that HTTP request. The response is a ready report plus a signed snapshot receipt. It does not depend on another serverless request finding a process-local job.
4. The frontend retains only this current report in module memory and tab session storage (`premium_current_report`), replacing the previous one. It restores an unexpired snapshot after reload; it does not maintain a saved-report list or database collection.
5. PDF download posts the complete snapshot and its separate receipt to `/api/premium-reports/pdf`, with administrator authentication. The renderer uses that calculation without provider calls or rescoring.

The receipt is an HS256 JWT bound to the administrator subject, the `premium-report-snapshot` audience, a canonical report SHA-256 digest and a 30-minute expiry. Integral floats normalize to integers so an unchanged JavaScript JSON round trip preserves the digest. Snapshot encoding is limited to 2 MB. Invalid or expired snapshots are rejected; do not modify a signed snapshot to upgrade old report contents. Recalculate instead.

## Compatibility endpoints

Requests omitting `delivery` still default to the older background flow: return HTTP 202 and poll `/api/premium-reports/{id}`. Those jobs are temporary process memory, expire after 30 minutes, and have a limit of 20 entries. Two generation slots bound concurrency. They do not survive a server restart or guarantee affinity across serverless instances. The current frontend uses inline generation; polling remains for legacy responses/links.

Legacy PDF links are report-scoped, one-use capabilities with a two-minute lifetime. New snapshots use the authenticated PDF POST instead. Neither admin tokens nor snapshots are put into URLs. Legacy in-memory state does not recreate saved report history.

## Data freshness and deployment

The dashboard caches resolved provider observations for 15 minutes per symbol/requested basis/period. Benchmark observations have their own 15-minute cache. Recalculate produces a new scoring run but may consume still-valid cached inputs; it is not a guarantee of an immediate provider refresh.

Deploy both frontend and backend. `backend/vercel.json` gives `server.py` a 300-second function budget; the backend deployment must use the matching project root/entrypoint. Instance memory may be reused as a cache, but inline snapshots do not rely on instance reuse for later PDF delivery.

Runtime settings are loaded by the existing server configuration: CMS authentication/signing settings, FinEdge/Upstox connector credentials, and normal application/database settings. Keep credentials in environment configuration. No new report collection, external model worker, Python subprocess or machine-learning service is required.

## Reader-facing output

The website and PDF show category scores, factor pros/cons, mixed/unavailable factors, input completeness, financial history and key ratios. They omit weights, raw scoring equations, input hashes and provider-request diagnostics. The internal signed snapshot retains those engineering details for reproducibility. An older current snapshot may lack newer review fields; the page asks for recalculation rather than inventing missing commentary.

Scoring and PDF functions are tested independently of live providers. Source-recovery, parity, snapshot integrity, legacy polling and frontend rendering checks are listed in the [implementation guide](premium-model-implementation.md#presentation-completeness-and-validation).
