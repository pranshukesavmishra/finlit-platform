-- One row per company per day the score was computed, so the site can show "score change since last quarter".
CREATE TABLE IF NOT EXISTS score_history (
    symbol    text     NOT NULL,
    statement text     NOT NULL,
    model     text     NOT NULL,
    day       date     NOT NULL,
    overall   smallint,
    pillar_quality smallint, pillar_growth smallint, pillar_profitability smallint, pillar_balance smallint, pillar_technical smallint,
    PRIMARY KEY (symbol, statement, model, day)
);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT ON score_history TO finlit_api;
        GRANT SELECT ON ingest_runs, ingest_queue, companies, snapshots TO finlit_api;
    END IF;
END
$$;
