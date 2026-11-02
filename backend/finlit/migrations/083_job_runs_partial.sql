-- A job that finished with its essential step done but one or more optional steps failed (fund facts: scheme master ok, expense ratios or fund size not) is
-- recorded as 'partial' (shown as "degraded" by the supervisor), not as a failed run. See finlit/jobs/supervisor.py.
ALTER TABLE job_runs DROP CONSTRAINT IF EXISTS job_runs_status_check;
ALTER TABLE job_runs ADD CONSTRAINT job_runs_status_check CHECK (status IN ('running', 'ok', 'partial', 'failed', 'killed', 'timeout', 'skipped'));
