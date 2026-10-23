-- Mutual fund dashboard (/funds browsed by category; see finlit/mf.py "dashboard").
--
-- mf_schemes gains the figures the category table shows and sorts by, so the list stays one plain query:
--   sip3y, sip5y   yearly rate (XIRR, percent) of a monthly SIP of equal amounts over the last 3 / 5 years, valued at the latest NAV
--   mdd3y_m        largest fall between month-end NAVs over the last 3 years (percent, 0 or negative): one measure for every scheme
--   aum_lakh       fund size, all plans of the scheme together, rupees lakh (AMFI quarterly average; else the fund house's month-end net assets)
--   ter            expense ratio of this scheme's own plan (percent a year), AMFI's TER file
--   chk_*          the plain checklist (finlit.mf.CHECKS): bits passed, bits that could be checked, and their counts
-- mf_monthly   one row per active Growth scheme: its month-end NAVs (last NAV of each calendar month) for the last five years and a bit, about
--              60 points. SIP returns and the month-end fall are worked out from it for every scheme, also those whose daily series is not kept.
ALTER TABLE mf_schemes
    ADD COLUMN IF NOT EXISTS sip3y     double precision,
    ADD COLUMN IF NOT EXISTS sip5y     double precision,
    ADD COLUMN IF NOT EXISTS mdd3y_m   double precision,
    ADD COLUMN IF NOT EXISTS aum_lakh  double precision,
    ADD COLUMN IF NOT EXISTS aum_asof  date,
    ADD COLUMN IF NOT EXISTS aum_kind  text,              -- 'q': AMFI quarterly average; 'm': month-end net assets from the portfolio file
    ADD COLUMN IF NOT EXISTS ter       double precision,
    ADD COLUMN IF NOT EXISTS ter_date  date,
    ADD COLUMN IF NOT EXISTS chk_pass  smallint,
    ADD COLUMN IF NOT EXISTS chk_known smallint,
    ADD COLUMN IF NOT EXISTS chk_bits  smallint,          -- bit i set: check i passed (bit 5: the return check used 5 years, else 3)
    ADD COLUMN IF NOT EXISTS chk_mask  smallint;          -- bit i set: check i could be worked out
CREATE INDEX IF NOT EXISTS mf_schemes_category_idx ON mf_schemes (category);

CREATE TABLE IF NOT EXISTS mf_monthly (
    code       integer PRIMARY KEY REFERENCES mf_schemes(code) ON DELETE CASCADE,
    days       date[] NOT NULL,                  -- ascending, one per calendar month: the day of that month's last NAV
    navs       double precision[] NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT ON mf_monthly TO finlit_api;   -- the API only reads; the worker writes
    END IF;
END
$$;
