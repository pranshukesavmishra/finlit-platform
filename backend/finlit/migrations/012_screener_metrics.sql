-- Every screener filter value for a company, in one JSON object, so the screener never parses snapshots at request time.
ALTER TABLE scores ADD COLUMN IF NOT EXISTS metrics jsonb;
ALTER TABLE scores ADD COLUMN IF NOT EXISTS industry text;

-- Index membership (NIFTY 50, NIFTY Bank, ...) from the public constituent lists.
CREATE TABLE IF NOT EXISTS index_members (
    index_code text NOT NULL,
    symbol     text NOT NULL,
    PRIMARY KEY (index_code, symbol)
);
CREATE INDEX IF NOT EXISTS index_members_symbol_idx ON index_members (symbol);
