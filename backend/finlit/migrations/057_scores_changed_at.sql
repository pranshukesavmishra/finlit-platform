-- When a score row last changed in ANY way. updated_at only moves when a report is scored (the nightly rescoring reads it as "how old is this score"),
-- while the live-quote job rewrites a row's figures every minute without touching it. The screener table asks for "rows changed since X" with this,
-- so it re-reads only what moved instead of the whole table.
ALTER TABLE scores ADD COLUMN IF NOT EXISTS changed_at timestamptz NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS scores_changed_idx ON scores (model, changed_at);
