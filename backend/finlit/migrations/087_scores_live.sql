-- Real-time scores (docs/REALTIME-SCORES.md). `scores.live_at` is the moment the price-driven part of a FinLit IQ (the Technical pillar and the overall score)
-- was last worked out again from a live quote, between two full builds. `updated_at` stays "the last full build" so the data-freshness check still
-- notices a nightly batch that did not run. The screener shows the newer of the two as `scored_at`. Idempotent.
ALTER TABLE scores ADD COLUMN IF NOT EXISTS live_at timestamptz;
