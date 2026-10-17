-- Extra columns so the screener and company comparison need no per-company lookups.
ALTER TABLE scores
    ADD COLUMN IF NOT EXISTS name             text,
    ADD COLUMN IF NOT EXISTS pb               numeric(10,2),
    ADD COLUMN IF NOT EXISTS roce             numeric(10,2),
    ADD COLUMN IF NOT EXISTS debt_to_equity   numeric(10,2),
    ADD COLUMN IF NOT EXISTS sales_cagr       numeric(10,2),
    ADD COLUMN IF NOT EXISTS profit_cagr      numeric(10,2),
    ADD COLUMN IF NOT EXISTS operating_margin numeric(10,2),
    ADD COLUMN IF NOT EXISTS change_pct       numeric(10,2),
    ADD COLUMN IF NOT EXISTS return_1m        numeric(10,2),
    ADD COLUMN IF NOT EXISTS return_1y        numeric(10,2);
