-- When each ETF's candles were last fetched successfully. A resumed refresh (refresh-etf --resume) skips the ETFs fetched after the
-- latest market close, so a retry after a partial night asks Upstox only for what failed (see finlit/etf.py refresh).
ALTER TABLE etf_funds ADD COLUMN IF NOT EXISTS fetched_at timestamptz;
