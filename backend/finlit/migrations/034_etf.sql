-- ETFs (exchange-traded funds listed on NSE): what the exchange list, Upstox prices/candles and AMFI's NAV file say. Filled once a night by
-- `refresh-etf` (finlit/etf.py); the public API only reads. Nothing here is ever deleted by the job: a fund that leaves the list is marked
-- inactive, and a short or empty answer from a provider leaves the stored row untouched.
--
-- Size (measured on the real list, 355 ETFs, 10 years of daily candles = 335,000 prices): history is kept as ONE row per ETF with packed arrays
-- (dates 4 bytes, close 8 bytes each) instead of ~335,000 narrow rows with an index. About 4 MB of raw values before compression,
-- against about 25 MB for the narrow table, which matters on a free 0.5 GB database.
CREATE TABLE IF NOT EXISTS etf_funds (
    symbol          text PRIMARY KEY,                 -- NSE trading symbol, e.g. NIFTYBEES
    isin            text NOT NULL,
    instrument_key  text NOT NULL,                    -- Upstox key, NSE_EQ|<ISIN>
    exchange_name   text NOT NULL,                    -- the exchange's own (often ugly) name
    short_name      text,                             -- Upstox's cleaner name, when it sends one
    scheme_name     text,                             -- AMFI's registered scheme name, when the ISIN matches
    fund_house      text,                             -- AMFI's fund house, without the words "Mutual Fund"
    display_name    text NOT NULL,
    category        text,                             -- key in finlit/etf.py CATEGORIES; NULL = not derivable from the names
    asset_class     text,
    active          boolean NOT NULL DEFAULT true,
    -- latest price (the last close in the stored series; the day's quote is added once the market has closed)
    price           double precision,
    prev_close      double precision,
    change_pct      double precision,
    price_date      date,
    volume          bigint,
    avg_turnover    double precision,                 -- average of close x volume over the last 20 sessions, rupees
    -- computed from the stored series (finlit/etf.py build_metrics); NULL when not computable, the reason is in `reasons`
    ret_1m          double precision,
    ret_6m          double precision,
    ret_1y          double precision,
    ret_3y          double precision,
    ret_5y          double precision,
    cagr_3y         double precision,
    cagr_5y         double precision,
    vol_1y          double precision,
    mdd_1y          double precision,
    mdd_3y          double precision,
    mdd_5y          double precision,
    high52          double precision,
    low52           double precision,
    range_from      date,                             -- first day the 52-week range covers (later than a year ago for a young ETF)
    first_date      date,                             -- first price in our data (10 years back at most), NOT the launch date
    points          integer NOT NULL DEFAULT 0,
    break_date      date,                             -- price history before this day is withheld (suspected split or bad data)
    reasons         jsonb NOT NULL DEFAULT '{}'::jsonb,
    extra           jsonb NOT NULL DEFAULT '{}'::jsonb,
    -- AMFI NAV
    nav             double precision,
    nav_date        date,
    nav_premium     double precision,                 -- (close on nav_date / NAV - 1) x 100, only when the ETF traded on the NAV's own day
    first_seen      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS etf_funds_active_idx ON etf_funds (active, avg_turnover DESC NULLS LAST);

-- One row per ETF. highs/lows/volumes hold the last ~260 sessions only (52-week range, traded value) and line up with the END of `dates`.
CREATE TABLE IF NOT EXISTS etf_history (
    symbol     text PRIMARY KEY REFERENCES etf_funds(symbol) ON DELETE CASCADE,
    dates      date[]             NOT NULL,
    closes     double precision[] NOT NULL,
    highs      double precision[] NOT NULL DEFAULT '{}',
    lows       double precision[] NOT NULL DEFAULT '{}',
    volumes    double precision[] NOT NULL DEFAULT '{}',
    full_at    timestamptz NOT NULL DEFAULT now(),   -- last time the whole 10 years were re-fetched (the nightly run only adds the last weeks)
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- One line per nightly run: what it did and why it stopped, kept for the last 60 runs.
CREATE TABLE IF NOT EXISTS etf_runs (
    id          bigserial PRIMARY KEY,
    started_at  timestamptz NOT NULL,
    finished_at timestamptz NOT NULL DEFAULT now(),
    status      text NOT NULL,
    detail      jsonb NOT NULL DEFAULT '{}'::jsonb
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT ON etf_funds, etf_history, etf_runs TO finlit_api;
    END IF;
END
$$;
