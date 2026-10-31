-- Background job supervisor (finlit/jobs, docs/JOBS.md): every run of every scheduled job, and one row of current state per job.
-- job_runs is the history (what ran, how it ended, why it did not start); job_state is what the supervisor decides from and what GET /api/jobs/status shows.
CREATE TABLE IF NOT EXISTS job_runs (
    id          bigserial PRIMARY KEY,
    job         text        NOT NULL,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status      text        NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'ok', 'failed', 'killed', 'timeout', 'skipped')),
    reason      text,
    attempt     integer     NOT NULL DEFAULT 1,
    exit_code   integer,
    duration_s  real,
    peak_rss_mb integer,
    pid         integer,
    counts      jsonb       NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS job_runs_job_idx ON job_runs (job, started_at DESC);
CREATE INDEX IF NOT EXISTS job_runs_running_idx ON job_runs (status) WHERE status = 'running';

CREATE TABLE IF NOT EXISTS job_state (
    job                  text PRIMARY KEY,
    first_seen_at        timestamptz NOT NULL DEFAULT now(),
    last_success_at      timestamptz,
    last_attempt_at      timestamptz,
    last_status          text,
    next_due_at          timestamptz,
    consecutive_failures integer     NOT NULL DEFAULT 0,
    retry_at             timestamptz,
    held_until           timestamptz,
    held_reason          text,
    forced_at            timestamptz,          -- the freshness checker found this job's data stale and asked for a run now
    forced_attempts      integer     NOT NULL DEFAULT 0,
    state                text        NOT NULL DEFAULT 'idle',   -- idle | due | waiting | running | held | disabled
    state_reason         text,
    updated_at           timestamptz NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT ON job_runs, job_state TO finlit_api;
        GRANT USAGE ON SEQUENCE job_runs_id_seq TO finlit_api;
    END IF;
END $$;
