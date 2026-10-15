-- FinLit platform: market data + precomputed research snapshots.
-- Runs on plain Postgres 16; when TimescaleDB is installed, price_daily becomes a hypertable.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     text PRIMARY KEY,
    applied_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS companies (
    symbol            text PRIMARY KEY,
    name              text NOT NULL,
    nse_code          text,
    bse_code          text,
    has_consolidated  boolean NOT NULL DEFAULT true,
    sector            text,
    industry          text,
    updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS companies_name_idx ON companies (lower(name));

CREATE TABLE IF NOT EXISTS price_daily (
    symbol  text        NOT NULL,
    day     date        NOT NULL,
    open    numeric(14,2),
    high    numeric(14,2),
    low     numeric(14,2),
    close   numeric(14,2) NOT NULL,
    volume  bigint,
    PRIMARY KEY (symbol, day)
);

-- One row per (stock, statement basis, section). `body` is the exact JSON the API sends,
-- so the ETag computed at write time stays valid byte for byte.
CREATE TABLE IF NOT EXISTS snapshots (
    symbol        text        NOT NULL,
    statement     text        NOT NULL CHECK (statement IN ('consolidated', 'standalone')),
    section       text        NOT NULL,
    body          text        NOT NULL,
    etag          text        NOT NULL,
    generated_at  timestamptz NOT NULL,
    PRIMARY KEY (symbol, statement, section)
);

-- Flat score table for the screener and sorting; never parsed out of JSON at request time.
CREATE TABLE IF NOT EXISTS scores (
    symbol               text        NOT NULL,
    statement            text        NOT NULL,
    model                text        NOT NULL,
    overall              smallint,
    band                 text,
    pillar_quality       smallint,
    pillar_growth        smallint,
    pillar_profitability smallint,
    pillar_balance       smallint,
    pillar_technical     smallint,
    price                numeric(14,2),
    market_cap           numeric(18,2),
    pe                   numeric(10,2),
    roe                  numeric(10,2),
    dividend_yield       numeric(8,2),
    sector               text,
    updated_at           timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, statement, model)
);
CREATE INDEX IF NOT EXISTS scores_overall_idx ON scores (model, overall DESC NULLS LAST);

CREATE TABLE IF NOT EXISTS ingest_runs (
    id           bigserial PRIMARY KEY,
    symbol       text        NOT NULL,
    statement    text        NOT NULL,
    status       text        NOT NULL,
    calls        integer,
    duration_ms  integer,
    errors       jsonb       NOT NULL DEFAULT '{}'::jsonb,
    started_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz
);
CREATE INDEX IF NOT EXISTS ingest_runs_symbol_idx ON ingest_runs (symbol, started_at DESC);

-- Stocks someone opened before they were ingested; the worker drains this first.
CREATE TABLE IF NOT EXISTS ingest_queue (
    symbol        text        NOT NULL,
    statement     text        NOT NULL,
    requested_at  timestamptz NOT NULL DEFAULT now(),
    attempts      smallint    NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol, statement)
);
