# Launch runbook: from this repo to a live, secure FinLit site

Do the parts in order. Every command assumes the company email owns the accounts. Total time for a first
deploy: about half a day. Estimated cost: DigitalOcean about US$24/month, domain about US$10/year, everything else free.

## What runs where

| Piece | Where | Repo |
|---|---|---|
| Website (React) | Cloudflare Pages | `finlit-platform/frontend` |
| Research service (stock reports) | VPS container `research-api` + `worker` | `finlit-platform/backend` |
| Site backend (blog, portfolio, contact, chat, admin) | VPS container `site-api` | `Financial-Portfolio/backend` (unchanged) |
| Databases | VPS: Postgres+Timescale, MongoDB, Redis | compose file |
| Public door | Cloudflare Tunnel to `api.finlitventures.com` | compose file |
| Backups, files, model files | Cloudflare R2 | |

Temporary hosting before the real domain: use `finlit.pages.dev` for the website and skip the tunnel by
testing the API from your laptop (see step 9). Sign-in cookies need the real domain, so keep accounts for later.

## Staging without the domain (do this first)

You do not need finlitventures.com to go live for testing.
1. Skip steps 1 and 3 (domain, tunnel). Open ports 80 and 443 on the DigitalOcean firewall.
2. In `.env` add `API_HOST=<server-ip-with-dashes>.sslip.io`, `ACME_EMAIL=<company email>`, `STAGING_ORIGIN=https://finlit.pages.dev`.
3. Start with: `docker compose -f deploy/docker-compose.prod.yml -f deploy/docker-compose.staging.yml --env-file .env up -d`
4. GitHub variable `VITE_API_BASE=https://<API_HOST>`; the Pages project `finlit` gives `https://finlit.pages.dev`.
5. Use a throwaway admin password for staging.

**Moving to finlitventures.com later (about 15 minutes, no rebuild):** add the domain to Cloudflare, create the
tunnel for `api.finlitventures.com`, close ports 80 and 443, change `VITE_API_BASE`, `ALLOWED_HOSTS` and
`CORS_ORIGINS`, attach the domain to the Pages project, and redeploy.

## 0. Accounts (use the company email)

Create each with 2FA on (an authenticator app or security key): GitHub org access, Cloudflare, DigitalOcean,
FinEdge (you already have a key), Upstox (market ticker token), Resend or AWS SES (email), Google AI Studio
(Gemini chat key), Razorpay (later), Sentry (free).

## 1. Domain (Cloudflare)

1. Cloudflare dashboard → Domain Registration → register `finlitventures.com` (or add the existing one and
   change its nameservers to Cloudflare).
2. SSL/TLS → set **Full (strict)**; turn on **Always Use HTTPS** and HSTS.

## 2. Server (DigitalOcean)

1. Create droplet: Bangalore (BLR1), Ubuntu 24.04, 4 GB / 2 vCPU, SSH key login only.
2. Cloud Firewall: **no inbound rules** at all (the tunnel connects outward). Allow SSH from your IP only if you
   need it, and remove that rule when finished.
3. On the server:

```bash
adduser deploy && usermod -aG sudo,docker deploy
# /etc/ssh/sshd_config: PermitRootLogin no, PasswordAuthentication no  then: systemctl restart ssh
apt update && apt install -y docker.io docker-compose-v2 unattended-upgrades fail2ban git
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
mkdir -p /opt/finlit && chown deploy /opt/finlit
```

## 3. Cloudflare Tunnel

1. Cloudflare → Zero Trust → Networks → Tunnels → Create (Cloudflared) → name `finlit-vps`. Copy the **token**.
2. Public hostname: `api.finlitventures.com` → HTTP → `caddy:8080`.
3. Keep the token for `CF_TUNNEL_TOKEN` below.

## 4. Configure secrets on the server

```bash
cd /opt/finlit && git clone https://github.com/pranshukesavmishra/finlit-platform.git . 
git clone https://github.com/Yusra-Khan532/financial-portfolio.git ../financial-portfolio
cp .env.example .env && chmod 600 .env
openssl rand -base64 32   # run once per secret below
```

Fill `.env` (never commit it):

```
ENVIRONMENT=production
POSTGRES_PASSWORD=...        REDIS_PASSWORD=...        MONGO_PASSWORD=...
FINEDGE_MODE=live            FINEDGE_API_KEY=...
CF_TUNNEL_TOKEN=...
# site backend (same names as today)
CMS_ADMIN_EMAIL=you@yourcompany.com
CMS_ADMIN_PASSWORD_HASH=...   # python -c "import bcrypt;print(bcrypt.hashpw(b'NEW-STRONG-PASSWORD',bcrypt.gensalt(12)).decode())"
CMS_JWT_SECRET=...            # 32+ random bytes
RESEND_API_KEY=...  SENDER_EMAIL=hello@finlitventures.com  CONTACT_RECIPIENT_EMAIL=you@yourcompany.com
UPSTOX_ACCESS_TOKEN=...  GEMINI_API_KEY=...
```

The research service refuses to start in production with default passwords, wildcard hosts or fixture data, and
says which setting is wrong.

## 5. Build and start

```bash
cd /opt/finlit
docker build -t ghcr.io/pranshukesavmishra/finlit-research:latest backend
docker build -f deploy/site-api/Dockerfile -t ghcr.io/pranshukesavmishra/finlit-site-api:latest ../financial-portfolio/backend
docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d
docker compose -f deploy/docker-compose.prod.yml ps     # all "healthy" or "running"
```

Create the read-only database user for the public API (limits damage if the API is ever compromised):

```bash
docker compose -f deploy/docker-compose.prod.yml exec db psql -U finlit -c \
  "CREATE USER finlit_api_user PASSWORD 'CHANGE-ME' IN ROLE finlit_api;"
# then add to .env:  API_DATABASE_URL=postgresql://finlit_api_user:CHANGE-ME@db:5432/finlit   and re-run `up -d`
```

## 6. Load the stock universe and first reports

```bash
RUN="docker compose -f deploy/docker-compose.prod.yml run --rm worker"
$RUN refresh-universe                      # all ~5,700 listed stocks for search
$RUN ingest RELIANCE TCS HDFCBANK INFY ICICIBANK BPCL IOC ITC SBIN LT
curl -s https://api.finlitventures.com/api/stocks/RELIANCE | head -c 300
```

Stocks nobody has opened yet are built on first request (the page shows "Preparing this report" for a few seconds).

Schedules: install `deploy/crontab` as `/etc/cron.d/finlit` (live quotes each minute in market hours,
fundamentals nightly, stock list weekly).

## 7. Website on Cloudflare Pages

1. Cloudflare → Workers & Pages → Create → Pages → **Direct upload** → project name `finlit` (gives `finlit.pages.dev`).
2. Custom domain: `finlitventures.com` and `www`.
3. GitHub repo → Settings → Environments → create `production` (required reviewer: you).
   - Variables: `VITE_API_BASE` = `https://api.finlitventures.com`
   - Secrets: `CLOUDFLARE_API_TOKEN` (create at Cloudflare → My Profile → API Tokens → Edit Cloudflare Pages only),
     `CLOUDFLARE_ACCOUNT_ID`.
4. Push to `main`: the "Website" workflow type-checks, builds and deploys.

## 8. Backups (do not skip)

1. Cloudflare → R2 → create buckets `finlit-backups`; create an API token limited to that bucket.
2. Nightly dumps (add to cron on the server):

```bash
docker compose -f deploy/docker-compose.prod.yml exec -T db pg_dump -U finlit -Fc finlit | age -r AGE_PUBLIC_KEY | rclone rcat r2:finlit-backups/pg/$(date +%F).dump.age
docker compose -f deploy/docker-compose.prod.yml exec -T mongo mongodump --archive -u finlit -p "$MONGO_PASSWORD" --authenticationDatabase admin | age -r AGE_PUBLIC_KEY | rclone rcat r2:finlit-backups/mongo/$(date +%F).archive.age
```

3. Keep the `age` private key offline. **Restore a backup into a scratch container once a month**; a backup you
   have never restored is not a backup. For point-in-time recovery later, move to WAL-G (see deployment-blueprint.md).

## 9. Verify before telling anyone

- [ ] `https://finlitventures.com` loads; the ticker, stock search (Ctrl+K), a stock page, blog and portfolio work.
- [ ] Contact form and a service enquiry arrive by email (and in Admin → Contact messages).
- [ ] `https://api.finlitventures.com/api/health` returns `{"ok":true}`; `/api/docs` returns 404.
- [ ] `curl -sI https://api.finlitventures.com/api/stocks/RELIANCE` shows `strict-transport-security`, `x-content-type-options` and an `etag`.
- [ ] Open the site on a phone (4G): the stock summary appears in under a second after the page loads.
- [ ] Admin login works with the **new** password (change the one that was shared in chat).
- [ ] Cloudflare → Security → turn on **WAF managed rules**, **Bot Fight Mode**, and a rate-limiting rule on
      `/api/content/admin/login` and `/api/contact`.
- [ ] Run `node frontend/e2e/smoke.mjs https://finlitventures.com` (needs a test admin account) or the dev version locally.

## 10. After launch

- Sentry (free) for the website and both APIs; an external uptime checker on `/api/health` and the home page;
  heartbeat pings from the cron jobs.
- Razorpay and real sign-in (email code, Google, passkeys): next build phase, described in `docs/platform-plan.md`.
- Before taking payments: privacy notice and terms reviewed by a lawyer, and a decision on SEBI Research Analyst
  registration (see `docs/deployment-blueprint.md`).
- Updating: `git pull`, rebuild images, `docker compose ... up -d` (migrations run first and must stay backward compatible).
