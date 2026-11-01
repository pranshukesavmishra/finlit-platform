# AWS memory and deployment health

Production runs the services in `deploy/aws/docker-compose.aws.yml` on the AWS host. The application container has a 1200 MB limit; PostgreSQL 640 MB, Redis 320 MB and Caddy/backup 128 MB each. These are ceilings, not reservations. The host also has swap configured by `deploy/aws/bootstrap.sh`.

- `deploy/start.sh` runs migrations, starts the site backend and job launcher, then serves the research API and website. The image health check uses `/api/ping`, which does not need a database query.
- `deploy/scheduler.sh` keeps the Python job supervisor and supporting loops alive. Scheduling, concurrency and memory gates belong to `backend/finlit/jobs/`; see [JOBS.md](../JOBS.md). Do not install a second host cron schedule for those jobs.
- Keep caches bounded and avoid reading whole report tables into memory. The image uses one research API worker, one site API worker and `MALLOC_ARENA_MAX=2`.
- PostgreSQL, Redis and Caddy have protected OOM priorities. Background jobs raise their own OOM score so a job is stopped before the website when possible.

If the site answers 503 after a deployment, inspect `deploy/aws/deploy.sh status` and `deploy/aws/deploy.sh logs app`. Check container health and host memory. Use the Console's data-load controls when investigating heavy jobs. If the new application build fails its health check, use `deploy/aws/deploy.sh rollback`; the auto-deploy timer also rolls back an unhealthy new build. Database migrations are not reversed by an image rollback. See [AWS-DEPLOY.md](../AWS-DEPLOY.md) for database backup and restore.

After a release run `scripts/smoke.sh <AWS-site-url>`. The repository-root `.github/workflows/platform-smoke.yml` provides the same checks on demand; scheduled checks require `FINLIT_SITE_URL`. No hosting keep-alive workflow is needed.
