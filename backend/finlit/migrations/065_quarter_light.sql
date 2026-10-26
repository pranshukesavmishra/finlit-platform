-- Quarter results for companies the site does not hold in full: one tiny row per company per quarter, written by `refresh-results-light`
-- from ONE provider call (the quarterly profit and loss). No snapshot, no score. The quarter results page reads a row's figures from the
-- company's full report when that is current, else from here. Only the latest 3 quarters per company are kept.
--   filled = true : the quarter's figures (same definitions as the full report: see results_light.py)
--   filled = false: the provider was asked and has no figures for this quarter yet (provider_latest = the newest quarter it does have)
CREATE TABLE IF NOT EXISTS quarter_light (
    symbol          text             NOT NULL,
    quarter         text             NOT NULL CHECK (quarter ~ '^[0-9]{4}-(03|06|09|12)$'),
    statement       text             NOT NULL CHECK (statement IN ('consolidated', 'standalone')),
    filled          boolean          NOT NULL,
    period_end      date,
    provider_latest date,
    revenue         double precision,
    operating_profit double precision,
    net_profit      double precision,
    eps             double precision,
    sales_yoy       double precision,
    profit_yoy      double precision,
    sales_qoq       double precision,
    profit_qoq      double precision,
    opm             double precision,
    npm             double precision,
    op_yoy          double precision,
    op_qoq          double precision,
    op_yoy_why      text,
    op_qoq_why      text,
    checked_at      timestamptz      NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, quarter)
);
CREATE INDEX IF NOT EXISTS quarter_light_checked_idx ON quarter_light (checked_at);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON quarter_light TO finlit_api;
    END IF;
END
$$;
