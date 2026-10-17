# Going live: free end-to-end setup (website, research API, database, site backend)

What you end up with, all on free tiers and all working together:

| Piece | Where | What it does |
|---|---|---|
| **finlit** (this repo) | Render web service | The website, the research API (screener, reports, accounts, plans, IPOs, news), and background jobs |
| **finlit-db / finlit-redis** | Render free Postgres + Redis | Company data, members, cache |
| **finlit-site-api** (the company's `Financial-Portfolio` backend) | Render web service | Blog and CMS, portfolio report, contact and enquiry forms, FinLit AI chat, market ticker |
| **MongoDB Atlas** | Free M0 cluster | The site backend's database |

The browser only ever talks to **finlit**; it passes the blog/portfolio/forms/chat requests on to **finlit-site-api**. Changing to your own domain later is one setting (see the end).

Everything below was tested together locally (full browser run through blog, CMS, uploads, portfolio, plans, screener, compare, watchlist, dashboard, sign-in).

---
## Step 1. Private GitHub repo for the site backend (5 min)
The company's code and data (portfolio statements, uploaded PDFs) must not go in a public repo.
1. On GitHub: **New repository → name `Financial-Portfolio` → Private**.
2. On your computer, unzip the file you were given and push it:
   ```bash
   cd Financial-Portfolio-main
   git init -b main && git add . && git commit -m "Site backend"
   git remote add origin https://github.com/<your-username>/Financial-Portfolio.git
   git push -u origin main
   ```
3. Apply the storage patch (so uploads and the portfolio report survive restarts on a free host). Copy `deploy/site-api/persist-storage.patch` from this repo, then:
   ```bash
   cd backend && patch -p1 < persist-storage.patch && cd .. && git commit -am "Keep uploads and portfolio report in MongoDB" && git push
   ```

## Step 2. Database for the site backend: MongoDB Atlas (5 min)
1. https://www.mongodb.com/cloud/atlas → sign up → create a **free M0** cluster (region: Mumbai or Singapore).
2. **Database Access** → add a user (username + strong password).
3. **Network Access** → **Add IP Address → Allow access from anywhere** (`0.0.0.0/0`); Render's addresses change.
4. **Connect → Drivers** → copy the connection string. It looks like `mongodb+srv://USER:PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority`.

## Step 3. The site backend service on Render (10 min)
Render dashboard → **New → Web Service** → connect the private `Financial-Portfolio` repo, then:
- **Root Directory:** `backend`
- **Runtime:** Python 3 · **Build Command:** `pip install -r requirements.txt` · **Start Command:** `uvicorn server:app --host 0.0.0.0 --port $PORT --workers 1`
- **Instance type:** Free · **Region:** Singapore

Environment variables (Add Environment Variable):
| Name | Value |
|---|---|
| `PYTHON_VERSION` | `3.12.7` |
| `MONGO_URL` | the Atlas connection string from step 2 |
| `DB_NAME` | `finlit` |
| `CMS_ADMIN_EMAIL` | the email you will use to log in to the blog/CMS admin |
| `CMS_ADMIN_PASSWORD_HASH` | a bcrypt hash of your chosen admin password: run `python3 -c "import bcrypt,getpass;print(bcrypt.hashpw(getpass.getpass().encode(),bcrypt.gensalt()).decode())"` (install with `pip install bcrypt` first) |
| `CMS_JWT_SECRET` | any long random text (32+ characters): `python3 -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `ALLOWED_HOSTS` | the service's own host name, e.g. `finlit-site-api.onrender.com` (no `https://`) |
| `FINEDGE_API_KEY` | your FinEdge key (used by the CMS stock-fundamentals tools) |
| `GEMINI_API_KEY` | a Google AI Studio key: makes the **FinLit AI** chat work (https://aistudio.google.com/apikey, free tier) |
| `RESEND_API_KEY`, `SENDER_EMAIL`, `CONTACT_RECIPIENT_EMAIL` | for contact and enquiry emails (see "Email" below). Without them messages are still saved but not emailed. |
| `UPSTOX_ACCESS_TOKEN` | optional: powers the NIFTY ticker strip. Upstox tokens expire daily, so the strip hides itself when it is missing or expired. |

Wait for "Live", then open `https://<that-host>/api/` — it should show `{"message":"Nishant Jain PMS API"}`.

## Step 4. The main service: website + research API + databases (15 min)
1. Render → **New → Blueprint** → choose `pranshukesavmishra/finlit-platform`, branch `main` → **Apply**.
2. When asked: `FINEDGE_API_KEY` (paste), `ADMIN_EMAIL` and `ADMIN_PASSWORD` (your own administrator login; or leave empty and add later), `SITE_API_URL` = `https://<the host from step 3>` (for example `https://finlit-site-api.onrender.com`, no trailing slash).
3. After the first deploy open the service → **Environment** → copy `DEMO_PASSWORD`. Demo members (already confirmed): `demo-basic@finlit-demo.com`, `demo-silver@finlit-demo.com`, `demo-gold@finlit-demo.com`.
4. Open the service URL. Companies fill in from the background load, about 60 a minute. Raise `INGEST_LIMIT` (default 1500) to load more, up to every listed company (5,000+, a few hours).

## Step 5. Check everything (2 min)
```bash
cd frontend && npm ci && DEMO_PASSWORD=... node e2e/deploy_check.mjs https://<your-main-service>.onrender.com
```
It signs in as the demo members and checks the home page, deep links, the company universe, plans, watchlist, compare, IPO and news, and that Basic members don't get Silver/Gold data. Also open `/blog`, `/portfolio`, `/contact`, and log in at `/admin/login` with the CMS email and password from step 3.

## Keep it awake (free tier)
Free services sleep after 15 minutes idle (about a minute to wake) and sleeping pauses the background jobs. In the GitHub repo → **Settings → Secrets and variables → Actions → Variables** add `SITE_URL` = main service URL and `SITE_API_PING_URL` = `https://<site-api host>/api/`. The workflow *Keep the free servers awake* then pings both every 10 minutes.

---
## Email
- **Sign-up confirmation / password reset / alerts** (main service): with `ENVIRONMENT=staging` mail goes to the `outbox` table and is not sent, which is why the demo members exist. To send real mail you need a domain verified at https://resend.com: set `MAIL_MODE=resend`, `RESEND_API_KEY`, `MAIL_FROM` (an address on that domain). Until then Resend only delivers to your own account address.
- **Contact and enquiry forms** (site backend): `RESEND_API_KEY`, `SENDER_EMAIL`, `CONTACT_RECIPIENT_EMAIL` as above.

## Switching to your own domain (the "real" setup)
1. Render → main service → **Settings → Custom Domains** → add `finlitventures.com` (and `www`) and add the DNS records Render shows. HTTPS is automatic.
2. Main service environment: `ENVIRONMENT=production`, `PUBLIC_SITE_URL=https://finlitventures.com`, `CORS_ORIGINS=https://finlitventures.com,https://www.finlitventures.com`, `ALLOWED_HOSTS=finlitventures.com,www.finlitventures.com`, `MAIL_MODE=resend` with `RESEND_API_KEY` and `MAIL_FROM`. (Production mode refuses to start if any of these is unsafe and says which one.) Remove the demo members' `DEMO_PASSWORD` variable and delete the three demo accounts.
3. Create the first administrator: in the main service's Environment tab set `ADMIN_EMAIL` and `ADMIN_PASSWORD` (10+ characters) and redeploy. Sign in, then follow *Account → Security* to add the authenticator app (administrators must use it; `/console` stays closed until you do). Afterwards change the password in *Account* and delete `ADMIN_PASSWORD` from the environment.
4. Site backend environment: `CORS_ORIGINS=https://finlitventures.com`; add `finlitventures.com` to `ALLOWED_HOSTS` only if you point the domain at it directly.
For heavier traffic or no sleeping, upgrade the two services to Render's paid instance (about $7 each) or use the VPS route in `deploy/README.md`; nothing in the code changes.

## What runs in the background (main service, Indian time)
Same as `deploy/crontab`, run by `deploy/scheduler.sh` inside the container: live quotes every minute 09:00–15:59 on weekdays, price and watchlist alerts every 10 minutes then, other alerts (RSI, scores, results, filings) 19:30 on weekdays, nightly data refresh at 01:30, company list weekly (Sunday 02:15), saved-screen alert emails 07:30 on weekdays, weekly digest Sunday 18:30. Logs: `/tmp/job-*.log` and `/tmp/scheduler.log` in the container.

## Known limits of free tiers
- The free Postgres database expires after 30 days (Render deletes it). Before that, upgrade it or move to a paid database; export with `pg_dump` first.
- Sleeping and cold starts, as above. First request after a sleep can take about a minute.
- Upstox tokens expire daily, so the ticker strip depends on someone refreshing `UPSTOX_ACCESS_TOKEN`.
- The chat is rate limited to 10 messages a minute per visitor; Gemini's free tier has its own daily quota.
