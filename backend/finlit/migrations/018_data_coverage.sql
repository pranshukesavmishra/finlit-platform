-- What the data provider sent for each company against what its report shows (see finlit/coverage.py). One row per company and statement, rewritten on every rebuild.
CREATE TABLE IF NOT EXISTS data_coverage (
    symbol     text        NOT NULL,
    statement  text        NOT NULL,
    checked_at timestamptz NOT NULL DEFAULT now(),
    state      text        NOT NULL,              -- complete | partial | empty (what the provider sent)
    mismatches jsonb       NOT NULL DEFAULT '[]', -- the provider sent it but the report lacks it: always a bug
    detail     jsonb       NOT NULL DEFAULT '{}',
    PRIMARY KEY (symbol, statement)
);
CREATE INDEX IF NOT EXISTS data_coverage_bad_idx ON data_coverage (state) WHERE state <> 'complete' OR mismatches <> '[]'::jsonb;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON data_coverage TO finlit_api;
    END IF;
END
$$;
