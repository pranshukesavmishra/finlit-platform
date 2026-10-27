# Run the whole FinLit site on one AWS server (beginner runbook)

This replaces the free Render container. One small AWS server (EC2 `t3.small`, Mumbai) runs everything with Docker:
the website, the research API, the company site backend, the background jobs, its own PostgreSQL and Redis, and Caddy (the web server that gives you https).
It does not sleep, and the database is on the same machine, so pages are fast.

**Where the code comes from.** The server builds from the **company repository**: `https://github.com/Yusra-Khan532/Financial-Portfolio`, branch `main`, folder `finlit-platform/`
(the repository also holds the company's older `backend/` and `frontend/` folders; the server never builds those).
**Future changes are made in the company repository. To put them on the server, run `deploy.sh` (it pulls `main` and rebuilds).**
Your passwords and keys live only in `/opt/finlit/.env.aws` on the server: outside the git clone, so a pull never touches them, and never in any repository.

```
/opt/finlit/
  .env.aws                  your settings and secrets (only on the server)
  src/                      clone of the company repository
    finlit-platform/        <- the folder that is built (Dockerfile, deploy/aws/ ...)
  state/                    small notes (which commit runs)
```

Time needed: about 45 minutes the first time (most of it is the first build).

---

## 0. What you need
- An AWS account (free plan: $100 of credits, valid until 27 April 2027).
- Your keys, ready to paste: FinEdge API key (`FINEDGE_API_KEY`), the MongoDB Atlas connection string (`MONGO_URL`, optional but needed for blog/forms), an email and a strong password for the site administrator. Optional: `UPSTOX_ACCESS_TOKEN`, Dhan keys.
- Turn on **MFA for the AWS root user** and set a **billing alarm** now (section 11).

## 1. Create the server (AWS console, region **Asia Pacific (Mumbai) ap-south-1**)
1. EC2 > **Launch instance**. Name: `finlit`.
2. Image: **Ubuntu Server 24.04 LTS**, architecture **64-bit (x86)**.
3. Instance type: **t3.small** (2 vCPU, 2 GB RAM).
4. Key pair: **Create new key pair**, name `finlit`, type RSA, format **.pem**. The file downloads once. Keep it safe (section 10); AWS cannot give it to you again.
5. Network settings > create a security group with three rules: **SSH (22)** source **My IP**, **HTTP (80)** from anywhere, **HTTPS (443)** from anywhere.
6. Storage: **20 GiB gp3**.
7. Launch. Then EC2 > **Elastic IPs** > **Allocate Elastic IP address** > select it > **Associate** with the `finlit` instance.
   An Elastic IP keeps the address the same after a reboot or stop. AWS charges for **every** public IPv4 address, Elastic or not, about **$0.005 per hour = $3.65 per month**. This is the address you will use below as `YOUR.ELASTIC.IP`.

## 2. Connect from Windows with SSH
Put `finlit.pem` somewhere private, for example `C:\Users\YOU\.ssh\finlit.pem`.

**PowerShell** (Windows 10/11 has `ssh`):
```powershell
# one time: only you may read the key, otherwise ssh refuses ("UNPROTECTED PRIVATE KEY FILE")
icacls "$env:USERPROFILE\.ssh\finlit.pem" /inheritance:r
icacls "$env:USERPROFILE\.ssh\finlit.pem" /grant:r "$($env:USERNAME):(R)"
ssh -i "$env:USERPROFILE\.ssh\finlit.pem" ubuntu@YOUR.ELASTIC.IP
```

**Git Bash**:
```bash
chmod 400 ~/.ssh/finlit.pem          # same idea: private to you
ssh -i ~/.ssh/finlit.pem ubuntu@YOUR.ELASTIC.IP
```
Answer `yes` to the question about the host fingerprint the first time. The prompt changes to `ubuntu@ip-...:~$`: you are on the server. All commands below are typed there. (`exit` leaves.)

## 3. Prepare the server (once)
```bash
sudo install -d -o ubuntu -g ubuntu /opt/finlit
git clone https://github.com/Yusra-Khan532/Financial-Portfolio.git /opt/finlit/src
bash /opt/finlit/src/finlit-platform/deploy/aws/bootstrap.sh
```
The script updates Ubuntu, installs Docker (from Docker's own repository, signing key checked), makes a 2 GB swapfile (swappiness 10), turns on the firewall (22, 80, 443 only), fail2ban and automatic security updates, and prints what it did. It is safe to run again.

Optional, safer: let only your own address use SSH. Find your public address (search "what is my ip"), then run
`ADMIN_IP=203.0.113.7 bash /opt/finlit/src/finlit-platform/deploy/aws/bootstrap.sh`
**from that same address** (the script refuses if you are connected from another one, so you cannot lock yourself out). Without `ADMIN_IP`, SSH stays open to everyone but still needs your key, and fail2ban blocks guessers.

When it finishes, **log out and log in again** (`exit`, then the `ssh` command): that makes the `docker` group active.

## 4. Create the settings file
```bash
cp /opt/finlit/src/finlit-platform/deploy/aws/.env.aws.example /opt/finlit/.env.aws
chmod 600 /opt/finlit/.env.aws
```
Make the secrets (run each, copy the output line):
```bash
openssl rand -hex 24      # POSTGRES_PASSWORD     (run again for REDIS_PASSWORD)
openssl rand -base64 32   # SECRET_KEY            (run again for CMS_JWT_SECRET, and for DEMO_PASSWORD if you want demo accounts)
```
(The two database passwords use `-hex` because they sit inside a URL, which base64's `/ + =` would break.)

Edit the file (nano: type, `Ctrl+O` Enter to save, `Ctrl+X` to leave):
```bash
nano /opt/finlit/.env.aws
```
Replace every `CHANGE_ME_...`:

| Name | What to put |
|---|---|
| `PUBLIC_SITE_URL` | `http://YOUR.ELASTIC.IP` (later `https://your-domain`) |
| `POSTGRES_PASSWORD`, `REDIS_PASSWORD` | the two `-hex` values |
| `SECRET_KEY`, `CMS_JWT_SECRET` | the two `-base64` values (32+ characters) |
| `FINEDGE_API_KEY` | your FinEdge key |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | the real administrator (password 10+ characters, not containing the email name) |
| `MONGO_URL` | Atlas connection string (leave empty to run without blog/forms; the site still works). In Atlas > Network Access, add the Elastic IP. |
| `UPSTOX_ACCESS_TOKEN`, `DHAN_*`, `DEMO_PASSWORD` | optional; leave empty if unused |

Rules: no spaces around `=`, and no `$ " ' #` or spaces inside a value. `ADMIN_REQUIRE_MFA=1` stays (administrators need their authenticator app). Never paste this file into chat, email or git.

## 5. First deploy
```bash
bash /opt/finlit/src/finlit-platform/deploy/aws/deploy.sh
```
It checks the settings file (and stops with a clear message if a `CHANGE_ME` is left), pulls `main`, builds the image (6-12 minutes the first time), starts everything, waits for `/api/ping` and `/api/health`, and prints the address. Safe to rerun.

## 6. Open the site
Browse to `http://YOUR.ELASTIC.IP`. Sign in at `/login` with `ADMIN_EMAIL` / `ADMIN_PASSWORD`; the first sign-in asks you to set up an authenticator app. After that you may delete the `ADMIN_PASSWORD` line.
The database is empty at first. The background loader fills it (company list and prices first, then reports; hours for the full set). Pages for companies not yet loaded say "being prepared" and fill in by themselves.

## 7. Add a domain later (https)
1. At your domain registrar create a DNS **A record**: name `@` (and `www` if wanted) pointing to `YOUR.ELASTIC.IP`. Wait until `nslookup your-domain` shows that address.
2. `nano /opt/finlit/.env.aws`: set `DOMAIN=your-domain.com` and `PUBLIC_SITE_URL=https://your-domain.com`.
3. `bash /opt/finlit/src/finlit-platform/deploy/aws/deploy.sh`. Caddy gets a free certificate by itself and renews it. Ports 80 and 443 must stay open (they are).
(If you opened the site before the DNS record existed, wait a few minutes: Caddy retries.)

## 8. Everyday commands (on the server)
Make a shortcut once: `echo "alias finlit='bash /opt/finlit/src/finlit-platform/deploy/aws/deploy.sh'" >> ~/.bashrc && source ~/.bashrc`

| Do | Command |
|---|---|
| Update to the latest company code | `finlit` (= `deploy.sh`; pulls `main`, rebuilds, restarts, checks health) |
| Go back to the previous build | `finlit rollback` |
| What is running, health, memory, disk | `finlit status` |
| Logs (Ctrl+C to stop) | `finlit logs` or `finlit logs app` (also `db`, `redis`, `caddy`, `backup`) |
| Restart everything / one service | `finlit restart` / `finlit restart app` |
| Backup now / list backups | `finlit backup` / `finlit backups` |
| Any docker compose command | `finlit compose ps` |

Rollback note: the database only moves forward. A rollback returns the code, not data written meanwhile. Fix the problem in the company repository, then run `finlit` again (it always deploys the newest `main`).
Private repository? `export GIT_TOKEN=<read-only deploy token>` before running `deploy.sh`. It is passed to git through a throw-away helper and is never printed or stored. The default repository is public and needs nothing.
Different source? `REPO_URL`, `REPO_BRANCH`, `REPO_SUBDIR` can be set the same way.

## 9. Backups and restore
- A backup container saves the database **every night at 02:00 IST** into the `backups` Docker volume, keeps the newest **7**, and checks each file can be read. List them: `finlit backups`.
- **Copy the newest to your own computer now and then** (a backup on the same disk does not survive losing the server). On the server:
  `docker cp finlit-backup-1:/backups/FILENAME.dump ~/` then, on your computer: `scp -i finlit.pem ubuntu@YOUR.ELASTIC.IP:FILENAME.dump .`
- **Restore** (replaces the current database, after taking a safety backup first): `finlit restore FILENAME.dump`. It asks you to type `restore`.
- MongoDB data lives in Atlas (use its own backups); this server does not hold it.
- Changing `POSTGRES_PASSWORD` in the file later does **not** change the database's password (it is set when the database is first created). If you must change it: take a backup, `finlit compose down`, `docker volume rm finlit_pgdata`, edit the file, `finlit`, then `finlit restore` the backup.

### Moving the data from the old Render/Neon database
Only possible if the Neon database is still reachable (not blocked by its quota). On the server:
```bash
read -rs OLD_DATABASE_URL; export OLD_DATABASE_URL        # paste the old Neon connection string (direct, not "-pooler"), Enter; nothing is shown
finlit compose exec -T -e OLD_DATABASE_URL backup sh -c 'pg_dump --format=custom --no-owner --no-privileges --file=/backups/neon-import.dump "$OLD_DATABASE_URL"'
unset OLD_DATABASE_URL
finlit restore neon-import.dump
```
If `pg_dump` errors (quota, "project suspended"), the old data cannot be copied. **Honest note: in that case the new database starts empty.** It fills itself from the data providers (company data, prices, reports, scores) and the administrator account is created from `ADMIN_EMAIL`/`ADMIN_PASSWORD` at the first start. What cannot be rebuilt is anything only the old database held: **member accounts, watchlists, alerts, forum posts** are lost if the old database cannot be dumped.

## 10. Cost
Prices are approximate (Mumbai, on-demand, October 2026); check the AWS pricing page.

| Item | Per month |
|---|---|
| EC2 t3.small, always on | about $16-17 |
| 20 GB gp3 disk | about $2 |
| Public IPv4 (Elastic IP) | $3.65 |
| Data out (first 100 GB free) | about $0 |
| **Total** | **about $22** |

The $100 credit therefore lasts roughly 4 months of continuous running; the free plan ends 27 April 2027 whatever is left. **Set a billing alarm**: Billing > Budgets > create a budget (for example $30/month) with an email alert at 80%. Check the Billing page once a week at first. Stopping the instance stops the compute charge only; the disk and the IP keep billing; terminating the instance deletes the data (and releasing the Elastic IP stops its charge).

## 11. Security checklist
- [ ] `finlit.pem` stays on your computer only: never in git, email, chat or a shared drive. If it leaks, create a new key pair and replace the old key.
- [ ] SSH only from your address: the security group rule is "My IP" and `ADMIN_IP=... bootstrap.sh` was run (update both if your home address changes).
- [ ] **MFA turned on for the AWS root user**, and a billing alarm exists. Use an IAM user for daily work, not root.
- [ ] No secrets in git. The only place for them is `/opt/finlit/.env.aws` (permissions 600). `deploy.sh` re-applies `chmod 600` on every run.
- [ ] `ADMIN_REQUIRE_MFA=1` and the administrator's authenticator app is set up. Delete `ADMIN_PASSWORD` from the file afterwards (redeploy once).
- [ ] The database and Redis have no published ports; only 22, 80, 443 are open. Do not add rules for 5432 or 6379.
- [ ] Ubuntu security updates install themselves; once a month run `sudo reboot` at a quiet time if `/var/run/reboot-required` exists, then `finlit status`.
- [ ] A copy of a recent backup is on your own computer.
- [ ] Before real members arrive: set up e-mail (Resend), then `ENVIRONMENT=production`, `AUTO_VERIFY_EMAIL=0`, `MAIL_MODE=resend`, a real `DOMAIN` and `ALLOWED_HOSTS` (the app refuses to start in production otherwise).

## 12. Ten-minute check after a deploy
1. `finlit status`: all five containers `running`, `app` and `db` and `redis` `healthy`; memory not near the limit; disk under 60%.
2. Open `http://YOUR.ELASTIC.IP` (or the https address): the home page loads and refreshes quickly.
3. `curl -s http://YOUR.ELASTIC.IP/api/ping` prints `{"ok":true}`.
4. Sign in at `/login` as administrator; set up the authenticator app; open the admin Data health tab.
5. In the admin Data health tab the line "How this server sees you" shows **your own public address** (not `172.x`). That confirms rate limits and sign-in lockouts see the real visitor.
6. `cd /opt/finlit/src/finlit-platform && bash scripts/smoke.sh http://YOUR.ELASTIC.IP`. Right after the first deploy the data checks (for example the company count) FAIL because nothing is loaded yet; the page, API and health checks should pass. Run it again after a few hours.
7. `finlit backup` then `finlit backups`: a `.dump` file appears.
8. `finlit logs app`: no repeating errors (the first minutes show migrations and loads starting).
9. Reboot test (optional, once): `sudo reboot`, wait two minutes, reconnect, `finlit status`: everything came back by itself and the address is unchanged.
10. Write down: the Elastic IP, the key file location, where the settings file is (`/opt/finlit/.env.aws`), and the date the credits end (27 April 2027).

## Troubleshooting
- `deploy.sh` says "still has CHANGE_ME": open the file and fill the listed lines.
- Build ends with "Killed" or the server freezes: it ran out of memory. Check `free -h` shows swap, then rerun `finlit`.
- Site shows 502 for the first minutes after a start: the app is running migrations; `finlit logs app`.
- Atlas errors in `finlit logs app`: add the Elastic IP in Atlas Network Access, check `MONGO_URL`.
- https does not start: the DNS A record must point at the server; look at `finlit logs caddy`.
- Memory trouble in the background loads: set `BOOT_LOAD_ENABLED=0` or lower `INGEST_LIMIT`, then `finlit`.
