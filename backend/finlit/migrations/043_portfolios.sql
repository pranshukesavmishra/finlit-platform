-- Fund disclosures: what each fund house and AMFI publish about a scheme (finlit/disclosure.py). Filled by `refresh-disclosures` (daily between the 8th and
-- the 20th of the month, when the monthly portfolios appear); the public API only reads. Every stored row came from a parsed, validated official file; a
-- file that fails validation is reported and never stored; a short or odd answer never replaces a good row.
--
-- Everything hangs off the scheme FAMILY (mf_schemes.family: the plans and options of one scheme share their portfolio, TER row, benchmark ...).
--   (scheme key -> family is read straight from mf_schemes: an AMFI code, or the scheme's ISIN, which is also how an ETF is found)
--   disclosure_portfolios  one row per family and month-end, holdings packed in ONE jsonb array of arrays
--                          [name, isin, sector, class(e|d|c|o), pct, qty, value_lakh]; only the latest 3 month-ends are kept per family (the job prunes).
--   disclosure_facts       small facts per family and kind (aum_daily, aum_q, ter, benchmark, risk, launch, mininv), each with its date and source.
--   disclosure_isin        NSE ISIN -> symbol (about 2 600 rows), so a holding links to our stock page; the join to `companies` happens when reading.
--   disclosure_runs        which file bundle has been read for which month (resumable: a finished bundle is not read again).
-- finding a scheme by ISIN (ETF pages) must not scan the 14 000 schemes
CREATE INDEX IF NOT EXISTS disclosure_mf_isin_idx ON mf_schemes (isin);
CREATE INDEX IF NOT EXISTS disclosure_mf_isin2_idx ON mf_schemes (isin_reinvest);

CREATE TABLE IF NOT EXISTS disclosure_portfolios (
    fkey            text NOT NULL,
    as_of           date NOT NULL,
    amc             text NOT NULL,
    scheme_name     text NOT NULL,                  -- as the fund house's own file names it
    source          text NOT NULL,
    source_url      text NOT NULL,
    net_assets_lakh double precision,               -- the file's GRAND TOTAL, rupees lakh
    pct_total       double precision NOT NULL,      -- what the stored rows add up to (percent)
    n               integer NOT NULL,
    benchmark       text,                           -- as written in the file, when it gives one
    notes           jsonb NOT NULL DEFAULT '[]'::jsonb,
    holdings        jsonb NOT NULL,
    fetched_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (fkey, as_of)
);

CREATE TABLE IF NOT EXISTS disclosure_facts (
    fkey       text NOT NULL,
    kind       text NOT NULL,
    as_of      date,
    value      jsonb NOT NULL,
    source     text NOT NULL,
    source_url text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (fkey, kind)
);

CREATE TABLE IF NOT EXISTS disclosure_isin (
    isin   text PRIMARY KEY,
    symbol text NOT NULL
);

CREATE TABLE IF NOT EXISTS disclosure_runs (
    source     text NOT NULL,                       -- adapter key or feed name
    period     text NOT NULL,                       -- month 'YYYY-MM' of the bundle, or the feed's own period label
    status     text NOT NULL,                       -- done | partial
    detail     jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, period)
);
