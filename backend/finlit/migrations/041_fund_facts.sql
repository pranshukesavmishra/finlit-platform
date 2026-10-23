-- Fund facts from AMFI's own files (see finlit/disclosure.py). Mutual funds and ETFs alike: an ETF is an AMFI scheme too.
--
-- mf_facts   one row per AMFI scheme code: the scheme master's name of the scheme (shared by all its plans and options), launch date and
--            minimum amount, and the scheme code's own average AUM for the latest quarter AMFI published (rupees lakh). A whole quarter is
--            written at once and every other code's figure cleared in the same transaction, so two quarters are never mixed.
-- mf_ter     the latest total expense ratio (TER) of each scheme, Regular and Direct plan, keyed by the scheme name AMFI files it under.
CREATE TABLE IF NOT EXISTS mf_facts (
    code        integer PRIMARY KEY,
    base_name   text,                 -- "Axis Large Cap Fund": the scheme, without plan and option words (AMFI scheme master)
    name_key    text,                 -- base_name reduced to letters and digits, to find the TER row
    launch_date date,
    min_text    text,                 -- AMFI's wording of the minimum amount, e.g. "5000" or "Rs. 500 and in multiples of Rs. 500"
    aum_lakh    double precision,     -- average AUM of this scheme code over the quarter (rupees lakh), NULL when AMFI lists none
    aum_end     date,                 -- last day of that quarter
    aum_label   text,                 -- AMFI's name for the quarter, e.g. "July - September 2026"
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS mf_facts_name_key_idx ON mf_facts (name_key);

CREATE TABLE IF NOT EXISTS mf_ter (
    name_key    text PRIMARY KEY,
    name        text NOT NULL,
    category    text,
    ter_regular double precision,     -- percent a year; NULL when the scheme has no Regular plan (AMFI shows 0)
    ter_direct  double precision,     -- percent a year; NULL when the scheme has no Direct plan (every ETF: one plan, filed as Regular)
    ter_date    date NOT NULL,        -- the day this TER applies to (AMFI files one row per day)
    updated_at  timestamptz NOT NULL DEFAULT now()
);
