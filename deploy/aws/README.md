# FinLit on one AWS server (Docker Compose)

Full beginner runbook with every click and command: **[docs/AWS-DEPLOY.md](../../docs/AWS-DEPLOY.md)**. This page is the reference.

**Source of truth: the company repository** (`https://github.com/Yusra-Khan532/Financial-Portfolio`, branch `main`, folder `finlit-platform/`).
Future changes are made there. To update the server run `deploy.sh`: it pulls `main` and rebuilds. The server keeps its secrets in `/opt/finlit/.env.aws`, outside the clone, so a pull never touches them.

```
/opt/finlit/.env.aws            settings and secrets (server only; chmod 600; never in git)
/opt/finlit/src/                clone of the repository (REPO_URL, REPO_BRANCH)
/opt/finlit/src/finlit-platform build context and compose project (REPO_SUBDIR)
/opt/finlit/state/              which commit is running
```

## Files
| File | Purpose |
|---|---|
| `bootstrap.sh` | once, on the fresh server: updates, Docker (official repo), 2 GB swap, ufw, fail2ban, auto security updates, `/opt/finlit` |
| `.env.aws.example` | every setting with a safe placeholder and a one-line comment |
| `deploy.sh` | `deploy` (default), `rollback`, `status`, `logs [service]`, `restart`, `backup`, `backups`, `restore FILE`, `compose ARGS` |
| `docker-compose.aws.yml` | `app`, `db`, `redis`, `caddy`, `backup` |
| `Caddyfile` | https, compression, cache and security headers, proxy to the app |
| `backup.sh` | nightly dump with 7-day rotation, and the restore procedure (runs inside the `backup` container) |

## Quick start (on a fresh Ubuntu 24.04 server, as `ubuntu`)
```bash
sudo install -d -o ubuntu -g ubuntu /opt/finlit
git clone https://github.com/Yusra-Khan532/Financial-Portfolio.git /opt/finlit/src
bash /opt/finlit/src/finlit-platform/deploy/aws/bootstrap.sh        # then log out and back in
cp /opt/finlit/src/finlit-platform/deploy/aws/.env.aws.example /opt/finlit/.env.aws && chmod 600 /opt/finlit/.env.aws && nano /opt/finlit/.env.aws
bash /opt/finlit/src/finlit-platform/deploy/aws/deploy.sh
```
Overrides (environment variables for `deploy.sh`): `REPO_URL`, `REPO_BRANCH` (default `main`), `REPO_SUBDIR` (default `finlit-platform`), `FINLIT_HOME` (default `/opt/finlit`), `GIT_TOKEN` (private repository only: read-only deploy token, never printed or stored).

## Design
- **Memory (2 GB RAM + 2 GB swap):** Postgres `shared_buffers` 256 MB (container limit 640 MB), Redis `maxmemory` 256 MB with `allkeys-lru` and no persistence (limit 320 MB), app limit 1200 MB, Caddy and backup 128 MB each. Limits are ceilings; swappiness is 10.
- **Ports:** only Caddy publishes 80 and 443. `app` (8000), `db` and `redis` are reachable only inside the compose network. The firewall allows 22, 80, 443. (Docker bypasses ufw for published ports, which is why nothing else is published.)
- **TLS:** `DOMAIN` empty = plain http on the server's address. `DOMAIN=example.com` = automatic https (Let's Encrypt, renewed by Caddy; certificates are kept in the `caddy_data` volume).
- **Real visitor address:** Caddy overwrites `X-Forwarded-For` with the address it saw; the app has `CLIENT_IP_HEADER=x-forwarded-for` and reads the chain from the right, skipping private (Docker network) addresses, so no `TRUSTED_PROXIES` is needed.
- **Databases:** PostgreSQL (TimescaleDB image, same as `docker-compose.yml`) and Redis run here. MongoDB stays in Atlas (`MONGO_URL`); without it the app still starts (blog/forms say "not connected").
- **Rollback:** each deploy keeps the previous image as `finlit-app:previous`.

## Manual compose (normally use deploy.sh)
```bash
cd /opt/finlit/src/finlit-platform
ENV_FILE=/opt/finlit/.env.aws docker compose -p finlit -f deploy/aws/docker-compose.aws.yml --env-file /opt/finlit/.env.aws ps
```
