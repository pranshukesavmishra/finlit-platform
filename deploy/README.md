# Deploying to the VPS securely

The order matters. Do not point DNS at the server until step 4 is done.

## 1. Server basics (Ubuntu 24.04)

```bash
adduser deploy && usermod -aG sudo,docker deploy        # never run the app as root
# Copy your SSH public key to /home/deploy/.ssh/authorized_keys, then in /etc/ssh/sshd_config:
#   PermitRootLogin no
#   PasswordAuthentication no
#   KbdInteractiveAuthentication no
systemctl restart ssh
apt install -y unattended-upgrades fail2ban && dpkg-reconfigure -plow unattended-upgrades
```

Optional but recommended: reach SSH only over [Tailscale](https://tailscale.com) and close port 22 publicly.

## 2. Firewall: only Cloudflare may reach the web ports

```bash
ufw default deny incoming && ufw default allow outgoing
ufw allow from <your-admin-ip-or-tailscale-range> to any port 22 proto tcp
for ip in $(curl -s https://www.cloudflare.com/ips-v4) $(curl -s https://www.cloudflare.com/ips-v6); do
  ufw allow from $ip to any port 443 proto tcp
done
ufw enable
```

Only after this is it safe to set `CLIENT_IP_HEADER=cf-connecting-ip`. Nobody can bypass Cloudflare and fake the header.

## 3. Secrets and the read-only API user

```bash
cd /opt/finlit && cp .env.example .env && chmod 600 .env
# Fill in: ENVIRONMENT=production, FINEDGE_API_KEY, and POSTGRES_PASSWORD / REDIS_PASSWORD
# (generate each with: openssl rand -base64 32), plus:
#   ALLOWED_HOSTS=api.finlitventures.com,127.0.0.1
#   CORS_ORIGINS=https://finlitventures.com,https://www.finlitventures.com
#   CLIENT_IP_HEADER=cf-connecting-ip
docker compose up -d db redis migrate
docker compose exec db psql -U finlit -c "CREATE USER finlit_api_user PASSWORD '<random>' IN ROLE finlit_api;"
# Then in .env:  API_DATABASE_URL=postgresql://finlit_api_user:<random>@db:5432/finlit
docker compose up -d
```

The API refuses to start in production if any setting is unsafe, and the error names the problem.

## 4. TLS and Cloudflare

- Run Caddy (automatic HTTPS) on 443 in front of `127.0.0.1:8000`, or use a Cloudflare Origin Certificate.
- Cloudflare SSL mode **Full (strict)**, **Always Use HTTPS**, minimum TLS 1.2, HSTS on.
- Turn on Authenticated Origin Pulls, so the origin accepts only Cloudflare's client certificate.
- WAF: managed rules on, Bot Fight Mode on, and a rate-limiting rule on `/api/auth/*` once login ships.
- Cache rule: `api.finlitventures.com/api/stocks/*` caches and respects origin `Cache-Control`.

## 5. Backups (Postgres is the source of truth)

- Nightly `pg_dump` encrypted with `age` or `restic` and pushed to Cloudflare R2. Keep 30 days.
- **Test a restore every month.** A backup that has never been restored is not a backup.

## 6. Cron

Install `deploy/crontab` as `/etc/cron.d/finlit`.
