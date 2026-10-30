-- Mutual Fund Health Score upgrades (finlit/mfscore, docs/mf-score/README.md). Additive: nothing in mf_scores changes.
--
-- mf_score_history  one small row per scheme per ISO week (the last `score-mf` run of that week replaces the earlier ones, so a re-run is idempotent) with the
--                   final score, the four parts, the label, the status and the rank. Kept three years (`prune`). The latest score stays in mf_scores.
-- mf_score_alerts   a Gold member following a fund's score band ('band') or a move of N points between two weekly rows ('move'). Fired by `score-mf`, delivered
--                   through the same notifications table and mail path as the other alerts.
CREATE TABLE IF NOT EXISTS mf_score_history (
    key        text    NOT NULL,                 -- 'mf:<code>' or 'etf:<symbol>', as in mf_scores
    week       date    NOT NULL,                 -- Monday of the ISO week of run_date
    run_date   date    NOT NULL,
    kind       text    NOT NULL,
    code       integer,
    symbol     text,
    plan       text    NOT NULL,
    grp        text    NOT NULL,
    sub        text    NOT NULL,
    final      real,
    perf       real,
    risk       real,
    cost       real,
    quality    real,
    label      text,
    status     text    NOT NULL,
    rank       integer,
    rank_of    integer,
    percentile real,
    PRIMARY KEY (key, week)
);
CREATE INDEX IF NOT EXISTS mf_score_history_week_idx ON mf_score_history (week);
CREATE INDEX IF NOT EXISTS mf_score_history_code_idx ON mf_score_history (code, week DESC) WHERE code IS NOT NULL;
CREATE INDEX IF NOT EXISTS mf_score_history_symbol_idx ON mf_score_history (symbol, week DESC) WHERE symbol IS NOT NULL;

CREATE TABLE IF NOT EXISTS mf_score_alerts (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key        text        NOT NULL,
    name       text        NOT NULL,
    kind       text        NOT NULL CHECK (kind IN ('band', 'move')),
    points     real,                              -- 'move': the size of the move, in points
    channels   text[]      NOT NULL DEFAULT '{app}',
    status     text        NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused')),
    last_week  date,                              -- the week of the last run that looked at it: one message per weekly row at most
    fired_at   timestamptz,
    fired_count integer    NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, key, kind)
);
CREATE INDEX IF NOT EXISTS mf_score_alerts_key_idx ON mf_score_alerts (key) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS mf_score_alerts_user_idx ON mf_score_alerts (user_id);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT ON mf_score_history TO finlit_api;
        GRANT SELECT, INSERT, UPDATE, DELETE ON mf_score_alerts TO finlit_api;
    END IF;
END
$$;
