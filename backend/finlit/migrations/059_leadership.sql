-- Leader / In line / Laggard: how a stock's last 12 months compare with the peers in its industry and with two indices.
-- The label describes the past only. Written by the weekly job (finlit/leadership.py), read by /api/stocks/{symbol}/leadership.

-- The latest run: one row per stock that has a peer group.
CREATE TABLE IF NOT EXISTS leadership (
    symbol          text PRIMARY KEY,
    name            text,
    as_of           date NOT NULL,              -- the Friday this run is for
    group_id        text,
    group_name      text,                       -- "IT services"
    group_short     text,                       -- "IT"  (used in the sentence: "7th of 13 IT peers")
    group_kind      text,                       -- industry | sector (widened because the industry had fewer than 6 stocks)
    ranked          integer,                    -- stocks ranked in the group
    rank            integer,                    -- 1 = best 12-month return against the sector benchmark
    label           text,                       -- the PUBLISHED label: leader | in_line | laggard
    raw_label       text,                       -- this run's own answer
    label_since     date,                       -- the run on which the published label last changed
    direction       text,                       -- gaining | weakening | null
    rel13           real,                       -- fractions (0.05 = 5 points)
    rel26           real,
    rel52           real,
    rel52_market    real,
    sector_code     text,
    sector_name     text,
    sector_kind     text,                       -- index | peer_average
    sector_ret52    real,
    market_code     text,
    market_name     text,
    market_ret52    real,
    fundamental     text,                       -- below_peers | stronger_than_price | null
    fund_rank       integer,
    fund_n          integer,
    market_cap      numeric(18,2),
    held            boolean NOT NULL DEFAULT false,   -- a corporate-action gap was found: the label is held and a data alert raised
    stale_runs      integer NOT NULL DEFAULT 0,       -- weekly runs in a row with no fresh prices (flagged stale from 2)
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS leadership_group_idx ON leadership (group_id, rank);

-- Stocks the last run could not rank, and why (history | stale | liquidity | group): the stock page shows the matching empty state.
CREATE TABLE IF NOT EXISTS leadership_excluded (
    symbol     text PRIMARY KEY,
    reason     text NOT NULL,
    as_of      date NOT NULL
);

-- One row per run per stock, for the rank-history chart.
CREATE TABLE IF NOT EXISTS leadership_history (
    symbol        text NOT NULL,
    run_date      date NOT NULL,
    rank          integer,
    ranked        integer,
    label         text,
    direction     text,
    rel52         real,
    rel52_market  real,
    PRIMARY KEY (symbol, run_date)
);

-- "Has leadership held in this sector?": the quarterly backtest, one row per peer group.
CREATE TABLE IF NOT EXISTS sector_reliability (
    group_id      text PRIMARY KEY,
    group_name    text,
    tier          text NOT NULL,                -- consistent | mixed | not_reliable | insufficient
    hit_rate      real,                         -- share of checks where the top 30% beat the bottom 30% over the next 6 months
    checks        integer NOT NULL DEFAULT 0,
    periods       jsonb NOT NULL DEFAULT '[]',
    window_start  date,
    window_end    date,
    method        text NOT NULL DEFAULT 'rel12',
    computed_at   timestamptz NOT NULL DEFAULT now()
);

-- Configuration, not code: which sector index an industry is measured against, and which market index each size bucket uses.
-- New industries are added with a row; an industry without one is measured against the equal-weighted average of its peers.
CREATE TABLE IF NOT EXISTS leadership_benchmarks (
    industry      text PRIMARY KEY,             -- FinLit industry name, as shown on the stock page (compared ignoring case, "&" and punctuation)
    sector_code   text NOT NULL,                -- index code, e.g. NIFIT
    sector_name   text NOT NULL,
    group_name    text NOT NULL,                -- "IT services"
    group_short   text NOT NULL                 -- "IT"
);
CREATE TABLE IF NOT EXISTS leadership_market (
    bucket        text PRIMARY KEY,             -- large | mid | small (AMFI convention on market-cap rank: 1-100, 101-250, 251 and below)
    code          text NOT NULL,
    name          text NOT NULL
);

INSERT INTO leadership_benchmarks (industry, sector_code, sector_name, group_name, group_short) VALUES
    ('IT - Software', 'NIFIT', 'Nifty IT', 'IT software', 'IT software'),
    ('IT - Services', 'NIFIT', 'Nifty IT', 'IT services', 'IT services'),
    ('IT - Hardware', 'NIFIT', 'Nifty IT', 'IT hardware', 'IT hardware'),
    ('Banks', 'NIFBAN', 'Nifty Bank', 'banks', 'bank'),
    ('Pharmaceuticals & Biotechnology', 'NIFPHA', 'Nifty Pharma', 'pharma and biotech', 'pharma'),
    ('Automobiles', 'NIFAUT', 'Nifty Auto', 'automobile makers', 'auto'),
    ('Auto Components', 'NIFAUT', 'Nifty Auto', 'auto components', 'auto component'),
    ('Agricultural, Commercial & Construction Vehicles', 'NIFAUT', 'Nifty Auto', 'commercial vehicles', 'commercial vehicle'),
    ('Finance', 'NIFFINSER', 'Nifty Financial Services', 'finance companies', 'finance'),
    ('Capital Markets', 'NIFFINSER', 'Nifty Financial Services', 'capital market firms', 'capital market'),
    ('Insurance', 'NIFFINSER', 'Nifty Financial Services', 'insurers', 'insurance'),
    ('Diversified FMCG', 'NIFFMC', 'Nifty FMCG', 'FMCG', 'FMCG'),
    ('Personal Products', 'NIFFMC', 'Nifty FMCG', 'personal products', 'personal products'),
    ('Food Products', 'NIFFMC', 'Nifty FMCG', 'food products', 'food'),
    ('Beverages', 'NIFFMC', 'Nifty FMCG', 'beverages', 'beverage'),
    ('Household Products', 'NIFFMC', 'Nifty FMCG', 'household products', 'household products'),
    ('Consumer Durables', 'NIFCONDUR', 'Nifty Consumer Durables', 'consumer durables', 'consumer durables'),
    ('Healthcare Services', 'NIFHEAIND', 'Nifty Healthcare', 'healthcare services', 'healthcare'),
    ('Healthcare Equipment & Supplies', 'NIFHEAIND', 'Nifty Healthcare', 'healthcare equipment', 'healthcare equipment'),
    ('Realty', 'NIFREA', 'Nifty Realty', 'real estate', 'realty'),
    ('Media', 'NIFMED', 'Nifty Media', 'media', 'media'),
    ('Entertainment', 'NIFMED', 'Nifty Media', 'entertainment', 'entertainment'),
    ('Ferrous Metals', 'NIFMET', 'Nifty Metal', 'steel and iron', 'ferrous metal'),
    ('Non - Ferrous Metals', 'NIFMET', 'Nifty Metal', 'non-ferrous metals', 'non-ferrous metal'),
    ('Minerals & Mining', 'NIFMET', 'Nifty Metal', 'miners', 'mining'),
    ('Oil', 'NIFOILGAS', 'Nifty Oil & Gas', 'oil', 'oil'),
    ('Gas', 'NIFOILGAS', 'Nifty Oil & Gas', 'gas utilities', 'gas'),
    ('Petroleum Products', 'NIFOILGAS', 'Nifty Oil & Gas', 'petroleum products', 'petroleum'),
    ('Power', 'NIFENE', 'Nifty Energy', 'power', 'power'),
    ('Construction', 'NIFINF', 'Nifty Infrastructure', 'construction', 'construction')
ON CONFLICT (industry) DO NOTHING;
INSERT INTO leadership_market (bucket, code, name) VALUES
    ('large', 'NIF50',     'Nifty 50'),
    ('mid',   'NIFMID150', 'Nifty Midcap 150'),
    ('small', 'NIFSMA250', 'Nifty Smallcap 250')
ON CONFLICT (bucket) DO NOTHING;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON leadership, leadership_excluded, leadership_history, sector_reliability, leadership_benchmarks, leadership_market TO finlit_api;
    END IF;
END
$$;
