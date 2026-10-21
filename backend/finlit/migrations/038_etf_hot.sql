-- ETF hot / cold split (same idea as the stock side: a few names kept ready, the rest computed when someone opens them).
--
--   HOT  = the 100 most traded ETFs (average of close x volume over 20 sessions, from Upstox candles; see finlit/etf.py rank_hot).
--          Their 10-year packed candle history stays in etf_history, and their ready-made list rows live in etf_hot (and in Redis).
--   COLD = every other ETF. It keeps its narrow etf_funds row (price, 1-day / 1-year / 5-year returns and the other figures, computed every
--          night from the full 10 years), so lists, sorts and filters cover all of them. Its packed candle history is NOT kept in Postgres:
--          the chart is fetched from Upstox when the ETF is opened and cached in Redis for 14 days (see etf.py cold_history).
--
-- The nightly job (refresh-etf) re-ranks, rewrites etf_hot and deletes the packed history of ETFs that are no longer hot.
ALTER TABLE etf_funds ADD COLUMN IF NOT EXISTS turnover_rank integer;               -- 1 = most traded; NULL = no traded value (too few trading days)
ALTER TABLE etf_funds ADD COLUMN IF NOT EXISTS hot boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS etf_hot (
    rank      integer PRIMARY KEY,                                                  -- 1..100
    symbol    text NOT NULL UNIQUE REFERENCES etf_funds(symbol) ON DELETE CASCADE,
    body      jsonb NOT NULL,                                                       -- the list row exactly as /api/etf serves it
    built_at  timestamptz NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT ON etf_hot TO finlit_api;
    END IF;
END
$$;
