-- Category averages for the head-to-head Fund Compare (see finlit/mf_compare.py).
--
-- mf_cat_avg  one row per category and plan: an equal-weighted index of the category's active Growth schemes (one per fund), worked out once per
--             NAV date (the expensive part: up to 60 NAV histories) and kept packed like mf_history (about 3 bytes a point, ten years = ~8 KB).
--             A row with no blob says why there is no average (too few funds with NAV history); it is rebuilt when the category's NAV date moves on.
CREATE TABLE IF NOT EXISTS mf_cat_avg (
    category   text NOT NULL,                  -- mf_compare.cat_key of AMFI's category text, e.g. "equityschemeflexicap" (both of AMFI's wordings)
    plan       text NOT NULL,                  -- Direct | Regular
    nav_date   date NOT NULL,                  -- the category's newest NAV date when this was built
    d0         date,                           -- first day of the index
    n          integer NOT NULL DEFAULT 0,     -- points in the index
    blob       bytea,                          -- mf.pack_series(days, index values), the index starts at 100
    eligible   integer NOT NULL DEFAULT 0,     -- funds in the category on this plan (one Growth option each)
    members    integer NOT NULL DEFAULT 0,     -- funds whose NAV history went into the index
    codes      integer[] NOT NULL DEFAULT '{}',
    starts     date[] NOT NULL DEFAULT '{}',   -- first NAV day of each member in the index (members join on that day)
    note       text,
    built_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (category, plan)
);
ALTER TABLE mf_cat_avg ALTER COLUMN blob SET STORAGE EXTERNAL;   -- already compressed

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON mf_cat_avg TO finlit_api;   -- the API builds an average on the first request for a new NAV date
    END IF;
END
$$;
