-- FinLit Prism score history: one row per company, statement basis and Indian calendar day, so the score and its four parts can be drawn over time.
-- Written when a report is calculated (the score and the four parts) and by the daily technical refresh (the short- and long-term views). A column stays NULL
-- on a day it was not worked out; nothing is estimated and nothing is back-filled: the history starts on the day this table is first written.
CREATE TABLE IF NOT EXISTS prism_history (
    symbol         text        NOT NULL,
    statement      text        NOT NULL CHECK (statement IN ('consolidated', 'standalone')),
    day            date        NOT NULL,                  -- the Indian calendar day the figure was worked out
    model_version  text,                                  -- a jump in the line can be a new formula, not a changed business
    final          double precision,                      -- 0 to 100; NULL when no full calculation ran that day
    label          text,
    status         text,                                  -- RATED | PROVISIONAL
    p_fundamental  double precision,
    p_valuation    double precision,
    p_quality      double precision,
    p_risk         double precision,
    st_score       double precision,                      -- -100 to +100 technical views; NULL on a day it was not refreshed or was provisional
    lt_score       double precision,
    recorded_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, statement, day)
);
CREATE INDEX IF NOT EXISTS prism_history_day_idx ON prism_history (day);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON prism_history TO finlit_api;
    END IF;
END
$$;
