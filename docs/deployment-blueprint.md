# Deployment blueprint (Stage 1)

Researched October 2026; sources at the end. **Decision (Oct 2026):** the website talks to two backends.
- **Old Financial-Portfolio backend** (unchanged): blog/CMS, portfolio report, contact, service enquiries,
  chat assistant, market ticker and admin.
- **This repo's research service:** stock pages, the same FinEdge data and research model, precomputed so
  pages load in under a second.

## Shape

```
Browser ──► finlitventures.com              Cloudflare Pages (React app, static, free)
        └─► api.finlitventures.com           Cloudflare Tunnel (no open ports on the server)
                 └─► caddy (internal router on the VPS)
                       ├─ /api/stocks/admin/*  ─►  site-api   (old backend, MongoDB)
                       ├─ /api/stocks/*, /api/screener/*, /api/health ─► research-api (Postgres/Timescale + Redis)
                       └─ /api/*               ─►  site-api   (content, portfolio, contact, enquiry, chat, ticker)
```

## Decisions and why

| Area | Choice | Why |
|---|---|---|
| Server | **DigitalOcean Bangalore (BLR1), 4 GB** | Paid, predictable, support, data in India. Oracle's free ARM allowance was reportedly halved to 2 OCPU/12 GB on 15 Jun 2026, and idle instances get reclaimed: staging only. |
| Website | **Cloudflare Pages** via direct upload from GitHub Actions | Free for commercial use. SPA routing works with no `404.html`. Security headers come from `public/_headers`. |
| API exposure | **Cloudflare Tunnel** (`cloudflared` container) | No inbound ports at all. No TLS certificates on the box. |
| API host | **api.finlitventures.com** (not a /api proxy through Pages Functions) | Same-site with the main domain, so `__Host-` cookies work. Proxying through Pages Functions would use the 100k/day free Workers quota on every API call. |
| Domain | **Register finlitventures.com on Cloudflare now** (~US$10/yr) | `*.pages.dev` is a public suffix, so session cookies can't work across a temporary host. A published tunnel hostname needs a domain on Cloudflare DNS. |
| Backups | **WAL-G → R2** (7-day point-in-time) + weekly encrypted `pg_dump` (bucket-locked 30 days); MongoDB `mongodump` nightly → R2 | Monthly restore drill. Keys kept offline too. |
| Images and deploy | GHCR images → gated `production` environment → SSH via Cloudflare Access to a forced-command deploy user | Port 22 closed. Migrations run before containers are swapped, and every migration must work with both the old and new code. |
| Email | **Amazon SES, Mumbai (ap-south-1)** for sign-in codes; Resend stays for the old backend's lead alerts for now | Processing in India. DKIM, custom MAIL FROM and DMARC on `auth.finlitventures.com`. |
| Monitoring | Sentry (free), external uptime + cron heartbeats, Grafana Cloud free via Alloy, rotated Docker logs | Costs nothing. |

## Memory budget on 4 GB

- Postgres `shared_buffers=1GB`
- Redis `maxmemory 256mb`
- MongoDB `--wiredTigerCacheSizeGB 0.5`
- 2 GB swap

Move to 8 GB when model inference runs on the box.

## Accounts to create (with the company email)

1. **Cloudflare:** register the domain, turn on 2FA, create a Pages project `finlit`, a Tunnel, and R2 buckets
   `finlit-pg`, `finlit-dumps`, `finlit-models`, `finlit-archive`.
2. **DigitalOcean:** droplet in BLR1, Ubuntu LTS, cloud firewall with no inbound rules.
3. **GitHub:** environments `preview` and `production`. Secrets: `CLOUDFLARE_API_TOKEN` (Pages:Edit only),
   `CLOUDFLARE_ACCOUNT_ID`, the Access service token, the deploy SSH key.
4. **AWS:** SES in ap-south-1. Request production access.
5. **Razorpay:** test keys first, webhook secret.
6. **Sentry, Grafana Cloud, uptime checker.**
7. **MongoDB:** either the bundled container on the VPS (default) or MongoDB Atlas Mumbai.

## Order of setup

1. Domain and Cloudflare account.
2. Droplet hardening.
3. R2 buckets and tokens.
4. Compose stack: timescale (with WAL-G), redis, mongo, research-api, worker, site-api, caddy, cloudflared.
5. Tunnel hostnames.
6. First backup and restore drill.
7. Pages project and custom domain.
8. CI/CD workflows.
9. Sign-in, SES and Razorpay.
10. Monitoring.
11. Privacy notice, processor agreements and a SEBI RA registration decision before launch.

## Compliance notes

- **DPDP:** the main obligations apply from 13 May 2027. There is no general data-localisation rule yet.
  Encrypted R2 backups abroad are allowed today but must be recorded in the privacy notice.
- **Card data:** never stored. Only Razorpay IDs (RBI localisation applies to Razorpay).
- **SEBI:** CSCRF does not apply to RA-only registrants. Buy/sell recommendations need SEBI RA
  registration, which brings record-keeping duties.

## Sources

- Cloudflare Pages:
  - serving: https://developers.cloudflare.com/pages/configuration/serving-pages/
  - headers: https://developers.cloudflare.com/pages/configuration/headers/
  - limits: https://developers.cloudflare.com/pages/platform/limits/
  - direct upload from CI: https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/
- Tunnel:
  - with a firewall: https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-with-firewall/
  - quick tunnels: https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/
- R2:
  - S3 API: https://developers.cloudflare.com/r2/api/s3/api/
  - bucket locks: https://developers.cloudflare.com/r2/buckets/bucket-locks/
  - data location: https://developers.cloudflare.com/r2/reference/data-location/
- Public suffix list (pages.dev): https://github.com/publicsuffix/list
- Oracle free tier change: https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/
- WAL-G storage: https://wal-g.readthedocs.io/STORAGES/
- Timescale logical backup: https://docs.timescale.com/self-hosted/latest/backup-and-restore/logical-backup
- GHCR: https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry
- Resend regions: https://resend.com/docs/dashboard/domains/regions
- DPDP: https://www.hoganlovells.com/en/publications/indias-digital-personal-data-protection-act-2023-brought-into-force-
- SEBI cloud framework: https://www.sebi.gov.in/legal/circulars/mar-2023/framework-for-adoption-of-cloud-services-by-sebi-regulated-entities-res-_68740.html
