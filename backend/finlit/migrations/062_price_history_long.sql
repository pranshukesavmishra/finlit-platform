-- Weekly closes back to 2004 for the Leader / Laggard reliability backtest (finlit/history.py, `backfill-history`). The report's own price-MAX section only
-- reaches back about six years; this table holds the older part, one row per stock, as two parallel arrays (about 25 KB a stock).
CREATE TABLE IF NOT EXISTS price_history_long (
    symbol      text PRIMARY KEY,
    dates       date[] NOT NULL DEFAULT '{}',
    closes      real[] NOT NULL DEFAULT '{}',
    first_date  date,                          -- the oldest close the provider returned (null: nothing came back)
    tried_at    timestamptz NOT NULL DEFAULT now()
);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON price_history_long TO finlit_api;
    END IF;
END
$$;
