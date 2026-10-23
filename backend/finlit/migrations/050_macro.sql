-- India macro data (finlit/macro.py, worker refresh-macro): one row per series and period end, as published by MoSPI and the RBI.
-- macro_meta keeps what is not a time series: the latest RBI rates panel and WSS reserves breakdown, detected repo changes, the last
-- published page payload (so the page survives a Redis flush) and each step's last run.
CREATE TABLE IF NOT EXISTS macro_points (
    series  text             NOT NULL,
    d       date             NOT NULL,
    v       double precision NOT NULL,
    PRIMARY KEY (series, d)
);
CREATE TABLE IF NOT EXISTS macro_meta (
    key        text        PRIMARY KEY,
    body       jsonb       NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON macro_points, macro_meta TO finlit_api;
    END IF;
END
$$;
