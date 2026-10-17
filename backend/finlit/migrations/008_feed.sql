-- News, company filings, result dates and documents in one table. Exchange announcements are added automatically when a company is
-- loaded (auto = true, de-duplicated); administrators add curated items and result dates by hand.
CREATE TABLE IF NOT EXISTS feed_items (
    id         bigserial PRIMARY KEY,
    kind       text        NOT NULL CHECK (kind IN ('news', 'result', 'document')),
    title      text        NOT NULL,
    symbol     text,
    company    text,
    source     text,
    link       text,
    item_date  date        NOT NULL,
    category   text,
    period     text,
    summary    text,
    auto       boolean     NOT NULL DEFAULT false,
    dedupe     text        UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS feed_kind_date_idx ON feed_items (kind, item_date DESC);
CREATE INDEX IF NOT EXISTS feed_symbol_idx ON feed_items (symbol, item_date DESC);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON feed_items TO finlit_api;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO finlit_api;
    END IF;
END
$$;
