# Deployment

Production uses the AWS kit in [`aws/`](aws/README.md). Follow [`docs/AWS-DEPLOY.md`](../docs/AWS-DEPLOY.md) for setup and [`docs/TEAM-DEPLOY.md`](../docs/TEAM-DEPLOY.md) for everyday releases.

- `aws/docker-compose.aws.yml`: application, PostgreSQL, Redis, Caddy and backups.
- `../Dockerfile`: builds the website and both Python services from `finlit-platform/`.
- `start.sh`: migrates the database and starts the site API, job launcher and research API.
- `scheduler.sh`: keeps the Python job supervisor and supporting loops running. Scheduling rules live in `backend/finlit/jobs/registry.py`; see [`JOBS.md`](../docs/JOBS.md).

The root `docker-compose.yml` remains for local development. Render, Vercel, separate VPS/staging Compose files, static-hosting publish workflows and host crontab deployment are retired. Never run a second scheduler alongside the AWS job supervisor.
