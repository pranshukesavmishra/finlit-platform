-- IPO calendar. Entered and kept up to date by administrators; the public page reads it.
CREATE TABLE IF NOT EXISTS ipos (
    id            serial PRIMARY KEY,
    name          text        NOT NULL,
    symbol        text,
    kind          text        NOT NULL DEFAULT 'mainboard' CHECK (kind IN ('mainboard', 'sme')),
    sector        text,
    open_date     date        NOT NULL,
    close_date    date        NOT NULL,
    listing_date  date,
    price_low     numeric(12,2),
    price_high    numeric(12,2),
    lot_size      integer,
    issue_size_cr numeric(14,2),
    listing_price numeric(12,2),
    note          text,
    link          text,
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CHECK (close_date >= open_date)
);
CREATE INDEX IF NOT EXISTS ipos_open_idx ON ipos (open_date DESC);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON ipos TO finlit_api;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO finlit_api;
    END IF;
END
$$;
