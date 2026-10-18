# Going live: free end-to-end setup (website, research API, databases, site backend)

One Render Blueprint deploys everything from this repository; the only thing created by hand is a free MongoDB database.

| Piece | What it does |
|---|---|
| **finlit** (Render web service, from `backend/` + `frontend/`) | The website, the research API (screener, reports, accounts, plans, IPOs, news), and the background jobs |
| **finlit-site-api** (Render web service, from `site-api/`) | The company's site backend: blog and CMS, portfolio report, contact and enquiry forms, FinLit AI chat, ticker |
| **finlit-db, finlit-redis** (Render free Postgres + Redis) | Company data, members, cache |
| **MongoDB Atlas** (free M0, you create it) | The site backend's database |

The browser only talks to **finlit**; it passes the blog/portfolio/forms/chat requests on to **finlit-site-api** over Render's private network.
Tested together locally (clean database, full browser run: blog, CMS, uploads, portfolio, plans, screener, compare, watchlist, dashboard, sign-up and sign-in).

## Step 1. MongoDB Atlas (5 minutes)
1. https://www.mongodb.com/cloud/atlas → sign up → create a **free M0** cluster (region Mumbai or Singapore).
2. **Database Access** → add a user (username + strong password).
3. **Network Access** → **Add IP Address → Allow access from anywhere** (`0.0.0.0/0`); Render's addresses change.
4. **Connect → Drivers** → copy the connection string: `mongodb+srv://USER:PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority` (put your real password in place of `PASSWORD`).
If the company already has a live Mongo database with its blog and portfolio content, use its connection string instead and the existing content appears.

## Step 2. Deploy (10–15 minutes)
1. https://render.com → sign in with GitHub, allow access to `pranshukesavmishra/finlit-platform`.
2. **New → Blueprint** → choose the repository, branch `main` → **Apply**. Render asks for these values:

| Name | Value |
|---|---|
| `FINEDGE_API_KEY` | the FinEdge key (asked once, used by both services) |
| `MONGO_URL` | the Atlas connection string from step 1 |
| `CMS_ADMIN_EMAIL` / `CMS_ADMIN_PASSWORD` | the login for the blog/CMS admin at `/admin/login` (password 10+ characters) |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | the administrator of the research site (members, plan requests, data health at `/console`); password 10+ characters, must not contain the email name. Sign in, then add the authenticator app under *Account → Security* |

3. Wait for both services to say **Live** (the first build takes 5–8 minutes).
4. In the **finlit** service → **Environment**, copy `DEMO_PASSWORD`. The demo members (already confirmed) are
   `demo-basic@finlit-demo.com`, `demo-silver@finlit-demo.com`, `demo-gold@finlit-demo.com`.
5. Open the **finlit** URL. Companies load in the background, about 60 a minute (the 10 largest within a minute or two). Raise `INGEST_LIMIT` (default 1500) in the Environment tab to load more, up to every listed company (5,000+, a few hours).

## Step 3. Optional keys (any time, in the **finlit-site-api** Environment tab)
| Name | Makes this work |
|---|---|
| `GEMINI_API_KEY` | the **FinLit AI** chat (free key at https://aistudio.google.com/apikey) |
| `RESEND_API_KEY`, `SENDER_EMAIL`, `CONTACT_RECIPIENT_EMAIL` | emails for the contact and enquiry forms (messages are always saved; see "Email" below) |
| `UPSTOX_ACCESS_TOKEN` | the NIFTY ticker strip. Upstox tokens expire daily, so the strip hides itself when the token is missing or expired |

## Step 4. Check everything (2 minutes)
```bash
cd frontend && npm ci && DEMO_PASSWORD=... node e2e/deploy_check.mjs https://<your-finlit-service>.onrender.com
```
It signs in as the demo members and checks the home page, deep links, the company universe, plans, watchlist, compare, IPO and news, and that Basic members do not receive Silver/Gold data. Also open `/blog`, `/portfolio`, `/contact` and `/admin/login`.

## Keep it awake (free tier)
Free services sleep after 15 minutes idle (about a minute to wake), which also pauses the background jobs and the private link between the two services. In the GitHub repo → **Settings → Secrets and variables → Actions → Variables** add `SITE_URL` (the **finlit** URL) and `SITE_API_PING_URL` (`https://<finlit-site-api host>/api/`). The workflow *Keep the free servers awake* then pings both every 10 minutes.
If the blog or portfolio ever shows "waking up", wait a few seconds and reload. If the private link does not work on your Render plan, set `SITE_API_URL=https://<finlit-site-api host>` on **finlit**; it overrides the private address.

## New members and email
- **Sign-up in this staging setup** (`AUTO_VERIFY_EMAIL=1` in `render.yaml`): a new account is confirmed immediately and the visitor is told to sign in. This setting is refused in production mode.
- **Real confirmation emails** need a domain verified at https://resend.com: set `MAIL_MODE=resend`, `RESEND_API_KEY`, `MAIL_FROM` on **finlit**, and remove `AUTO_VERIFY_EMAIL`.

## Switching to your own domain (the "real" setup)
1. Render → **finlit** → **Settings → Custom Domains** → add `finlitventures.com` and `www`, add the DNS records Render shows. HTTPS is automatic.
2. On **finlit**: `ENVIRONMENT=production`, `PUBLIC_SITE_URL=https://finlitventures.com`, `CORS_ORIGINS=https://finlitventures.com,https://www.finlitventures.com`, `ALLOWED_HOSTS=finlitventures.com,www.finlitventures.com`, `MAIL_MODE=resend` with `RESEND_API_KEY` and `MAIL_FROM`; delete `AUTO_VERIFY_EMAIL` and `DEMO_PASSWORD` (and the three demo accounts). Production mode refuses to start if any of these is unsafe and says which one.
3. Delete `ADMIN_PASSWORD` once you have signed in and changed your password in *Account*.
For heavier traffic or no sleeping, move both services to Render's paid instance type (about $7 each) or to the VPS route in `deploy/README.md`; nothing in the code changes.

## When you make this repository private
Render keeps working (it has GitHub access to your repos). GitHub Pages for a private repo needs a paid GitHub plan; the live site does not depend on Pages. The company's content, including `site-api/`, stays in the repository's history, so keep it private.

## What runs in the background (Indian time)
Same as `deploy/crontab`, run by `deploy/scheduler.sh` inside **finlit**: live quotes every minute 09:00–15:59 on weekdays, price and watchlist alerts every 10 minutes then, other alerts (RSI, scores, results, filings) 19:30 on weekdays, nightly data refresh 01:30, company list weekly (Sunday 02:15), saved-screen emails 07:30 on weekdays, weekly digest Sunday 18:30. Logs: `/tmp/job-*.log`, `/tmp/scheduler.log`.

## Known limits of free tiers
- Free Postgres is deleted after 30 days. Upgrade it or export with `pg_dump` before then.
- Sleeping and cold starts, as above.
- Upload storage: CMS uploads and the portfolio report are kept in MongoDB and restored after every restart, so nothing is lost when a free instance restarts.
- The chat is limited to 10 messages a minute per visitor; Gemini's free tier has its own daily quota.
- `site-api/` is the company's code, copied here without the raw broker statements (`portfolio_data/sources/`); the report the site shows is `portfolio_data/current.json`. Upload new statements through the CMS admin.
