-- Mutual funds, built on AMFI's official NAV files (see finlit/mf.py).
--
-- mf_schemes   one row per AMFI scheme code (about 14,400, stopped ones included): identity, latest NAV and the numbers worked out from the
--              NAV history, so the list page is one plain query. Rows are never deleted: a scheme that drops out of the file just stops being "active".
-- mf_history   the daily NAV series of the schemes whose returns we work out (active Growth options), one packed row per scheme (about 3 bytes a
--              point instead of a 40-byte row per day: roughly 17 MB for the whole industry instead of 250 MB).
-- mf_backfill  which fund houses have had their five years of history loaded from AMFI (the load is resumable, one fund house at a time).
-- mf_meta      small key/value facts: the last refresh and what it did.
CREATE TABLE IF NOT EXISTS mf_schemes (
    code          integer PRIMARY KEY,
    name          text NOT NULL,
    isin          text,
    isin_reinvest text,
    amc           text NOT NULL,
    scheme_type   text NOT NULL,                 -- Open Ended / Close Ended / Interval Fund
    category      text NOT NULL,                 -- as AMFI's section header gives it, e.g. "Equity Scheme - Mid Cap Fund"
    plan          text NOT NULL,                 -- Direct | Regular | Unspecified
    option_class  text NOT NULL,                 -- Growth | IDCW | Other (IDCW covers dividend / payout / reinvestment; Other = AMFI states none)
    option_label  text,
    family        text NOT NULL,                 -- amc | category | name without plan and option words: groups the plans of one scheme
    nav           double precision,
    nav_date      date,
    prev_nav      double precision,
    prev_date     date,
    last_seen     date,                          -- newest NAV date in the last accepted file
    active        boolean NOT NULL DEFAULT true, -- still publishing NAVs (last NAV within a week of the newest in the file)
    has_hist      boolean NOT NULL DEFAULT false,
    r1m           double precision,              -- percent; 3Y and 5Y are annualised (CAGR), the others are point to point
    r6m           double precision,
    r1y           double precision,
    r3y           double precision,
    r5y           double precision,
    vol1y         double precision,
    vol3y         double precision,
    mdd           double precision,              -- maximum drawdown over the stored history (percent, negative)
    metrics_date  date,
    updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS mf_schemes_family_idx ON mf_schemes (family);
CREATE INDEX IF NOT EXISTS mf_schemes_amc_idx ON mf_schemes (amc);

CREATE TABLE IF NOT EXISTS mf_history (
    code       integer PRIMARY KEY REFERENCES mf_schemes(code) ON DELETE CASCADE,
    n          integer NOT NULL,
    d0         date NOT NULL,                    -- first NAV date stored
    d1         date NOT NULL,                    -- last NAV date stored
    blob       bytea NOT NULL,                   -- zlib( day gaps as uint16, NAV changes as int64 in 1e-8 units ), see mf.pack_series
    complete   boolean NOT NULL DEFAULT false,   -- true when AMFI's history was loaded back past the oldest day any return needs
    source     text NOT NULL DEFAULT 'amfi',
    updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE mf_history ALTER COLUMN blob SET STORAGE EXTERNAL;   -- already compressed

CREATE TABLE IF NOT EXISTS mf_backfill (
    amc_key    text PRIMARY KEY,
    amc        text NOT NULL,
    amc_id     integer,
    schemes    integer NOT NULL DEFAULT 0,
    points     integer NOT NULL DEFAULT 0,
    bytes      bigint NOT NULL DEFAULT 0,
    seconds    double precision NOT NULL DEFAULT 0,
    note       text,
    done_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mf_meta (
    key        text PRIMARY KEY,
    value      jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT ON mf_schemes, mf_history, mf_backfill, mf_meta TO finlit_api;   -- the API only reads; the worker writes
    END IF;
END
$$;
