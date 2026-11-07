# FinLit platform structure

`finlit-platform/` is the application source in the company repository, `Yusra-Khan532/Financial-Portfolio`. Development and AWS builds use this folder directly.

| Path | Purpose |
|---|---|
| `frontend/` | React + TypeScript website built with Vite. |
| `backend/finlit/` | Research API, authentication, PostgreSQL/Redis data layer and background jobs (**jobs NEVER stop: every scheduled job runs and completes every day; docs/JOBS.md**). |
| `site-api/backend/` | CMS, portfolio, forms, chat and premium model service; its Python dependencies are installed separately. |
| `Dockerfile`, `deploy/start.sh`, `deploy/scheduler.sh` | Combined AWS application image and startup. |
| `deploy/aws/` | Production Compose, deployment, rollback, Caddy, backups and auto-deploy timer. |
| `dev/`, `docker-compose.yml` | Local development. |
| `docs/prism/` | Premium model contract, inputs/outputs, scoring and technical-view documentation. |

CI and Dependabot configuration live in the repository root `.github/`; application checks run inside `finlit-platform/`. No other root application folder is needed.

Read [TEAM-DEPLOY.md](TEAM-DEPLOY.md) for contributions and releases, [AWS-DEPLOY.md](AWS-DEPLOY.md) for operations and [DHAN-SETUP.md](DHAN-SETUP.md) for market-data configuration and outstanding display-permission requirements.
