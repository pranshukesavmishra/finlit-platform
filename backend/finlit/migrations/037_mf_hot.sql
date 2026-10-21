-- Mutual funds, hot and cold (see finlit/mf.py).
--
-- mf_hot       the 100 schemes kept ready: their list row and their complete detail page, built each night, so they are answered in milliseconds
--              (and copied to Redis). Everything else is worked out when somebody opens it and kept only in Redis for a few days.
-- mf_history   now holds the packed NAV series of the hot schemes only (it was every active Growth scheme, about 23 MB). Every other scheme keeps
--              just its worked-out 1 year and 5 year returns (and the previous NAV for the 1 day change) in the narrow mf_schemes row.
CREATE TABLE IF NOT EXISTS mf_hot (
    code      integer PRIMARY KEY REFERENCES mf_schemes(code) ON DELETE CASCADE,
    rank      integer NOT NULL,
    basis     text NOT NULL,                  -- how the hot set was chosen (see mf.choose_hot)
    item      jsonb NOT NULL,                 -- the row as the list shows it
    detail    text NOT NULL,                  -- the finished detail JSON
    built_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS mf_hot_rank_idx ON mf_hot (rank);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT ON mf_hot TO finlit_api;   -- the API only reads; the worker writes
    END IF;
END
$$;
