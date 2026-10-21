-- One light row per listed company: what the provider's market-wide quote list says (price, day change, market cap, 52-week range, volume).
-- Filled once a night by `refresh-listing` (two provider calls, one short write), so the screener can list EVERY listed company,
-- not only the ones whose full report is stored. A company's full report (ratios, statements, growth) is still loaded on demand.
CREATE TABLE IF NOT EXISTS listing_quotes (
    symbol      text PRIMARY KEY,
    price       numeric(14,2),
    change_pct  numeric(10,2),
    market_cap  numeric(16,2),   -- Rs crore
    high52      numeric(14,2),
    low52       numeric(14,2),
    volume      bigint,
    traded_at   timestamptz,     -- when the provider says this price traded
    updated_at  timestamptz NOT NULL DEFAULT now()
);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON listing_quotes TO finlit_api;
    END IF;
END
$$;
