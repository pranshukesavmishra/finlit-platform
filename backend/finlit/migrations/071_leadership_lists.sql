-- Leader / In line / Laggard on the indicator's peer lists (finlit_technicals v1.1, see docs/technicals/README.md).
-- Written by the weekly job (finlit/leadership.py), read by /api/stocks/{symbol}/leadership. Everything here is additive: rows written before this
-- migration keep working (the new columns are null, and the page treats a null as "ranked among the data provider's industry peers").

-- Which kind of peer group ranked the stock, how many names its list holds and the date of that list.
ALTER TABLE leadership ADD COLUMN IF NOT EXISTS group_source text;        -- list (the indicator's peer list) | industry (the data provider's industry)
ALTER TABLE leadership ADD COLUMN IF NOT EXISTS group_listed integer;     -- names on the list (a list can hold names this site cannot rank)
ALTER TABLE leadership ADD COLUMN IF NOT EXISTS list_as_of date;          -- the date the peer lists are as of (27 Oct 2026 for the first delivery)

-- The weekly runs also keep this week's own answer and the 3-month figure (the indicator's weekly history shows both).
ALTER TABLE leadership_history ADD COLUMN IF NOT EXISTS raw_label text;
ALTER TABLE leadership_history ADD COLUMN IF NOT EXISTS rel13 real;

-- Peers that are on a group's list (or in its industry) but were not ranked this week, and why (history | stale | liquidity | no_prices | not_covered).
CREATE TABLE IF NOT EXISTS leadership_unranked (
    group_id  text NOT NULL,
    symbol    text NOT NULL,
    name      text,
    reason    text NOT NULL,
    as_of     date NOT NULL,
    PRIMARY KEY (group_id, symbol)
);

-- A company whose market cap is not known is measured against the Nifty 500 (the indicator's rule); the others follow the rupee cut-offs in leadership.py.
INSERT INTO leadership_market (bucket, code, name) VALUES ('unknown', 'NIF500', 'Nifty 500') ON CONFLICT (bucket) DO NOTHING;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON leadership_unranked TO finlit_api;
    END IF;
END
$$;
