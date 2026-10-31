"""Background job supervisor (docs/JOBS.md). registry: what the jobs are. due: when each is due. supervisor: runs them within the machine's limits and
watches them. state: history in Postgres. status: GET /api/jobs/status. freshness / canary: is the DATA current and right, whatever the jobs say."""
