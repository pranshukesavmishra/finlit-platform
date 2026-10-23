-- Mutual fund industry figures from AMFI's monthly category report (finlit/mf_insights.py): one row per scheme category and month, as AMFI
-- prints it, plus one row per month with the report's Grand Total. Filled by `refresh-industry` (daily; AMFI publishes around the 8th-10th of
-- the following month); the public API only reads. About 60 categories a month since April 2019: a few thousand rows in all.
--
-- mf_industry         one row per month and category. Amounts in rupees crore, as in the report. `section` is open | close | interval
--                     (AMFI's parts A, B and C) or fof_domestic (AMFI prints domestic fund of funds apart and leaves them out of its totals, so
--                     their money is not counted twice). `grp` is our grouping for the split: equity | debt | hybrid | solution | other | fof_domestic.
-- mf_industry_months  one row per month tried: the Grand Total of a stored report (status 'ok'), or why a month has no figures yet
--                     ('missing': AMFI has not published it; 'refused': the file failed its checks and nothing was stored from it).
CREATE TABLE IF NOT EXISTS mf_industry (
    month       date NOT NULL,                 -- first day of the report's month
    key         text NOT NULL,                 -- section/heading/category, reduced to letters and digits: unique within a month
    pos         smallint NOT NULL,             -- order in AMFI's table
    section     text NOT NULL,
    heading     text NOT NULL,                 -- AMFI's group heading, e.g. "Growth/Equity Oriented Schemes"
    category    text NOT NULL,                 -- AMFI's row label, e.g. "Mid Cap Fund"
    grp         text NOT NULL,
    schemes     integer,
    folios      bigint,
    mobilized   double precision,              -- funds mobilised during the month
    redemption  double precision,              -- repurchases and redemptions during the month
    net_flow    double precision,              -- net inflow (+) or outflow (-) for the month
    aum         double precision,              -- net assets under management at the end of the month
    aaum        double precision,              -- average net assets under management over the month
    PRIMARY KEY (month, key)
);

CREATE TABLE IF NOT EXISTS mf_industry_months (
    month       date PRIMARY KEY,
    status      text NOT NULL,                 -- ok | missing | refused
    why         text,                          -- the reason, for missing and refused
    schemes     integer,
    folios      bigint,
    mobilized   double precision,
    redemption  double precision,
    net_flow    double precision,
    aum         double precision,
    aaum        double precision,
    released    date,                          -- "Released on" in the file, when it says
    source_url  text,
    etag        text,                          -- AMFI's ETag of the stored file: the daily check asks "changed since?" and gets a tiny 304 when not
    sha256      text,
    n_rows      smallint,
    fetched_at  timestamptz NOT NULL DEFAULT now()
);
