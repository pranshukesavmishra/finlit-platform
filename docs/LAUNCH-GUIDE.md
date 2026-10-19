# FinLit Launch Guide: every step, in order

You will create three free accounts (Neon, MongoDB Atlas, Render), paste five values, and press Deploy: about 60 minutes of your time plus 15 minutes of waiting. Everything costs 0 for now.

**How people sign in today:** with an email address and a password. Anyone can open the site, click **Create account**, choose an email and a password, and sign in straight away. No email has to be sent or opened. One-time email codes and "Continue with Google" can be added later without changing anyone's account.

Never type a password, key or token into a chat. Secrets go only into the Render, Neon, Atlas and GitHub pages named below. Screen labels on those websites may differ slightly from these words; the order of actions is the same.

## Before you start

Have these ready:

1. **Your GitHub login.** Render will sign in with it.
2. **A NEW FinEdge API key** from your FinEdge dashboard. The old key was shown in an earlier chat, so do not reuse it. Keep the new one in a password manager or a private note.
3. **An email address** you check (for Neon, MongoDB Atlas and Render).
4. **One password for the administrator account**: 10+ characters and not containing the part of your email before the @. It also opens the blog/CMS tools: there is only one sign-in.
5. **About 60 minutes.**

What you will create:

| Where | What it holds | Cost |
| --- | --- | --- |
| Neon | The main database: members, plans, company data | Free |
| MongoDB Atlas | The blog, portfolio page and contact forms | Free (M0) |
| Render | Runs the website and both back ends in one service, plus a free cache | Free |
| GitHub (your repo) | Holds the code; Render builds from it | Free |

The code is already in your repository `pranshukesavmishra/finlit-platform`, branch `main`, including the company's back end in the `site-api` folder. You do not upload anything.

## What it costs

Everything below is 0 today. The last column says when you would start paying; nothing is charged unless you choose a paid plan yourself. Limits were read from each provider's own pages on 18 October 2026; Render's pricing page showed no prices, so none is quoted for Render.

| Service | Used for | Cost now | When you would need to pay |
| --- | --- | --- | --- |
| Render, free web service + free Redis | The whole site | 0 | When you need it to never sleep or need more memory: choose a paid instance (see Render's pricing page) |
| Neon, free Postgres | Members, plans, company data | 0 | If data passes 1 GB, or monthly compute passes 100 compute-hours (about 400 awake hours) |
| MongoDB Atlas, M0 free | Blog, portfolio, forms | 0 | If data passes 512 MB |
| UptimeRobot, free (optional) | Backup keep-awake check | 0 | Free plan: 50 monitors, checks every 5 minutes |
| Resend, free | Sign-up and contact emails | 0 | Free plan: 100 emails a day, 3,000 a month |
| Google AI Studio, free tier (Gemini 3.8 Flash) | FinLit AI chat | 0 | If the free per-minute or per-day limits (shown in AI Studio) are not enough: then you would turn on billing yourself |
| Domain finlitventures.com | Your own address | Ask your registrar | When the company signs off. Price depends on the registrar; check before buying |

## Step 1. Create the main database (Neon)

Neon gives a free Postgres database that does not expire (Render's own free database is deleted after 30 days, so it is not used).

1. Open https://neon.com and click **Sign up**. Choose **Continue with GitHub** (or Google).
2. When it asks you to create a project, enter: **Project name** `finlit`, **Postgres version** 16, **Region** AWS Asia Pacific (Singapore). Click **Create**.
3. On the project dashboard click **Connect**.
4. In the box that opens, switch **Connection pooling** OFF. The address in the string must not contain the word `-pooler`.
5. Click the copy button on the connection string. It looks like `postgresql://neondb_owner:XXXX@ep-something.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`.
6. Paste it into a private note and name it **DATABASE_URL**. You paste it into Render in Step 4.

**What you should see:** a project page with the Connect button and an empty database. Nothing to build: the website creates its own tables the first time it starts.

Free plan (from Neon's own pages): 1 GB of data, 100 compute-hours a month, it sleeps after 5 idle minutes, and the free plan has no time limit.

## Step 2. Create the blog database (MongoDB Atlas)

This holds the blog, the portfolio page and the contact forms. If the company already runs a live MongoDB with its blog content, ask them for that connection string and use it instead: the existing posts then appear.

1. Open https://www.mongodb.com/cloud/atlas and click **Try Free**. Sign up with Google or an email.
2. Create a cluster: choose the **M0 Free** plan, provider AWS, region Mumbai (or Singapore), name it `Cluster0`, click **Create**.
3. In the security step, create a database user: username `finlit`, click **Autogenerate Secure Password**, copy that password into your private note, click **Create User**.
4. Go to **Network Access** in the left menu, click **Add IP Address**, choose **Allow Access From Anywhere** (`0.0.0.0/0`), click **Confirm**. This is needed because Render's addresses change.
5. Go to **Database** in the left menu, click **Connect** on your cluster, choose **Drivers**, and copy the string that starts with `mongodb+srv://`.
6. In your private note, replace `<password>` in that string with the password from step 3. Name the result **MONGO_URL**.

**What you should see:** the cluster listed as running, one database user, and `0.0.0.0/0` under Network Access. The website creates its collections itself.

Free plan (from MongoDB's pages): 512 MB of data. A free cluster is paused after 30 days with no connections at all; the site connects every few minutes, so this will not happen while it is running.

## Step 3. Create the Render account and start the deploy

Render runs the whole site as one free service. Render gives each workspace about 750 free hours a month, which covers one service running all month and not two, so create **only this one free service** in the workspace.

1. Open https://render.com and click **Get Started**. Choose **GitHub** and authorize Render.
2. On the Render dashboard click **New +**, then **Blueprint**.
3. Under **Connect a repository** find `pranshukesavmishra/finlit-platform`. If it is not listed, click **Configure account** and give Render access to that repository.
4. Click **Connect** next to it. Leave the branch as `main`. Give the blueprint any name, for example `finlit`.
5. Render reads the file `render.yaml` and lists two items: **finlit** (web service, Free) and **finlit-redis** (Key Value, Free). Below them it asks for five values. Keep this page open and go to Step 4.

**What you should see:** both items marked Free, no database in the list (the database comes from Neon), and five empty value boxes.

## Step 4. Paste the five values Render asks for

Type or paste each value into its box on the Blueprint page, then click **Apply** (or **Deploy Blueprint**). Render hides secret values after you save.

| Name | What it is | Where it comes from |
| --- | --- | --- |
| `FINEDGE_API_KEY` | Market data for every company | A NEW key from your FinEdge dashboard |
| `DATABASE_URL` | The main database | Step 1: the Neon string, pooling OFF |
| `MONGO_URL` | The blog database | Step 2: the Atlas string with your real password |
| `ADMIN_EMAIL` | Your administrator login | Your own email address |
| `ADMIN_PASSWORD` | Your administrator password | You choose: 10+ characters, not containing the part of your email before the @ |

Render creates three more values for you, so do not type them: `SECRET_KEY`, `DEMO_PASSWORD` (the password of the demo accounts) and `CMS_JWT_SECRET` (the key that lets your normal administrator sign-in open the blog tools). Both halves of the site run in the same service, so they share `CMS_JWT_SECRET` automatically.

`SITE_API_URL` is not needed: the blog back end runs inside the same service and is found automatically. Set it only if the blog back end is ever hosted somewhere else.

**What you should see:** after Apply, a page with the service `finlit` and a build log scrolling.

## Step 5. Wait until it says Live, then open the site

1. Watch the **Logs** tab. The first build takes about 8 to 12 minutes because it builds the website and two Python environments.
2. When the service status turns **Live**, click the address under the service name: `https://finlit-xxxx.onrender.com`.
3. To read the demo password: service **Environment** tab, find `DEMO_PASSWORD`, click the eye icon.

**What you should see:** the FinLit home page. Companies appear in the background: the 10 largest within a couple of minutes, then about 60 a minute up to 1,500 companies. The Screener page shows the count growing.

The first visit after the site has been idle takes about a minute to wake: that is normal on the free plan.

## Step 6. Sign in for the first time, one account type at a time

Every account signs in at `/login`. There is no separate admin password form: `/admin/login` now just forwards you to `/login`.

| Account | Email | Password | What you should see after signing in |
| --- | --- | --- | --- |
| Demo Basic | `demo-basic@finlit-demo.com` | `DEMO_PASSWORD` | The dashboard with a Basic badge. Scores are locked on every company page except RELIANCE, the free example everyone can see |
| Demo Silver | `demo-silver@finlit-demo.com` | `DEMO_PASSWORD` | The dashboard with a Silver badge. FinLit scores and watchlists are open |
| Demo Gold | `demo-gold@finlit-demo.com` | `DEMO_PASSWORD` | The dashboard with a Gold badge. Everything is open: the FinLit model filters in the Screener, the Score screener and the Gold dashboards |
| A new visitor | Any email and a password of their own choice, using **Create account** on the sign-in page | Their own | "Your account is ready" at once (no email to open), then they sign in. They start on Basic |
| You, the administrator | The `ADMIN_EMAIL` you typed | The `ADMIN_PASSWORD` you typed | See below |

**First administrator sign-in, once only:**

1. Sign in at `/login` with your administrator email and password.
2. You are taken to **Account, Security**. Click to set up the authenticator app. Scan the picture with Google Authenticator, Microsoft Authenticator or Authy, type the 6-digit code, and confirm. Administrators must use this.
3. From now on, signing in asks for the 6-digit code after the password.
4. Open `/admin` (type it after your site address, for example `https://finlit-xxxx.onrender.com/admin`). The blog and content tools open at once, with no second password. The members, plans and data-health screen is at `/console`.
5. Change your password under **Account**, then delete `ADMIN_PASSWORD` in Render (service, Environment, delete the variable).

If `/admin` says the content tools are not connected, or the server answers `cms_not_configured`, the value `CMS_JWT_SECRET` is missing or shorter than 32 characters: add or regenerate it in the Environment tab, save, and let Render redeploy.

If a new member says they cannot sign in and the email service is not on yet, open `/console`, find them under members, and click **Confirm email**.

## Step 7. Keep the free site awake

A free Render service goes to sleep after 15 minutes without visitors and takes about a minute to wake. Sleeping also pauses the background data jobs. Two free pingers prevent this. Use both: the second is the backup for the first.

**7a. GitHub pinger (already in the code).**

1. Open your repository on GitHub, then **Settings**, **Secrets and variables**, **Actions**, tab **Variables**.
2. Click **New repository variable**. Name: `SITE_URL`. Value: your Render address, like `https://finlit-xxxx.onrender.com` (no slash at the end). Click **Add variable**.
3. Open the **Actions** tab, click **Keep the free server awake**, then **Run workflow**.

You should see a green tick. After that it calls `/api/ping` every 10 minutes. GitHub runs scheduled jobs on a best-effort basis, so a few minutes of delay is normal.

**7b. UptimeRobot (backup).**

1. Open https://uptimerobot.com and click **Register** (free).
2. Click **Add New Monitor**. Monitor Type: **HTTP(s)**. Friendly Name: `FinLit`. URL: `https://finlit-xxxx.onrender.com/api/ping`. Monitoring Interval: 5 minutes.
3. Click **Create Monitor**.

You should see the monitor turn green (Up). The free plan allows 50 monitors with 5-minute checks and can email you when the site is down.

The address `/api/ping` is used on purpose: it never touches the database, so these pings do not use up Neon's free compute hours.

Why only one service: 750 free hours cover about 744 hours in a 31-day month. If you ever create a second free web service in the same Render workspace, both would be suspended before the month ends. Do not.

## Step 8. Back up the databases every week

Free plans keep little or no backup history, so keep your own. This takes 5 minutes once a week; put a reminder in your phone. Do it on your own computer.

1. Install two tools once: the PostgreSQL client tools (`pg_dump`, version 16 or newer) and the MongoDB Database Tools (`mongodump`). If `mongodump` is missing, the script skips MongoDB.
2. In your terminal, inside the folder of the repository, run these four lines (use your own values from Steps 1 and 2; the passphrase is a long sentence you will remember):

```
export NEON_URL='postgresql://...your Neon string...'
export MONGO_URL='mongodb+srv://...your Atlas string...'
export BACKUP_PASSPHRASE='a long sentence only you know'
./scripts/backup.sh ~/finlit-backups
```

3. You get one encrypted file, for example `finlit-2026-10-25.tgz.enc` (about 8 MB at 160 companies). Copy it to a private place: a private Google Drive or OneDrive folder, or an external disk. Never put it in the GitHub repository: it contains member data. Delete copies older than 8 weeks. Store the passphrase in a password manager.
4. In MongoDB Atlas, also open your cluster, then **Backup**, and switch on backups: free clusters keep up to four daily snapshots.

To restore into an empty database: `openssl enc -d -aes-256-cbc -pbkdf2 -in finlit-DATE.tgz.enc | tar -xz -C restore`, then `pg_restore --no-owner -d "$NEON_URL" restore/postgres.dump` and `mongorestore --uri="$MONGO_URL" --archive=restore/mongo.archive --gzip`. The backup and restore of the main database were tested end to end: a restored copy had the same members and scores as the original.

## Step 9. Switch on the FinLit AI chat (free Google Gemini key)

The chat bubble ("Ask FinLit AI") answers questions about investing basics and the company's services. It uses Google's Gemini. Without a key it politely says it is unavailable, and the rest of the site works.

**Is it free?** Yes, on Google's free tier. Google's pricing page (read on 18 October 2026) lists the model the site uses, **Gemini 3.8 Flash**, as "Free of charge" for input and output on the Free tier, with no billing needed. Request limits per minute and per day are shown inside Google AI Studio (page "Rate limit"), and the daily limit resets at midnight Pacific time. If the free limit is reached, the chat says it is unavailable until the next reset; nothing is charged unless you switch on billing yourself.

**Important:** on the free tier Google states that content sent may be used to improve its products. The paid tier does not. So add one line to your Privacy notice (ask the company's legal adviser), and the chat already shows a notice not to share private financial details.

1. Open https://aistudio.google.com/apikey and sign in with a Google account (use a company or personal Google account you control).
2. If it asks you to accept the Terms of Service, read and accept. Google creates a default project for you.
3. Click **Create API key**. Choose the default project if asked. The key appears: click the copy button.
4. In Render open the service, **Environment** tab, **Add Environment Variable**. Name: `GEMINI_API_KEY`. Value: the key you just copied. Click **Save Changes**. Render redeploys in about 2 minutes.
5. Leave `GEMINI_MODEL` unset: the site then uses `gemini-3.8-flash`. Set `GEMINI_MODEL` only if Google ever retires that model; use the new model name from Google's model list, and check that the pricing page shows it as free.
6. Test: open the site, click **Ask FinLit AI**, type "What is a mutual fund?" and send.

**What you should see:** an answer within a few seconds. If you see "temporarily unavailable", see the troubleshooting table.

Never paste the key into a chat or a file in the repository. To replace it later: create a new key in AI Studio, change the value in Render, then delete the old key in AI Studio.

**Optional, the NIFTY ticker strip.** Add `UPSTOX_ACCESS_TOKEN` in the same way, with a token from your Upstox developer account. It expires every day, so the strip hides itself when the token has expired. Skip this if nobody will refresh it.

## Step 10. Real emails (later, needs your own domain)

Creating an account and signing in do **not** need email any more: a new account is confirmed the moment it is created (the setting `AUTO_VERIFY_EMAIL`). Email is only needed for: password-reset links, price and result alerts, the weekly summary, and notification of contact-form messages. Contact and enquiry messages are always saved and are visible to the administrator even without email.

Until this step is done: forgotten passwords cannot be reset by email, so tell a member who is locked out to create a new account with another email, or ask the engineer to set a new password for them. Alert emails are not sent (alerts still show inside the site).

Real email can only be sent from an address on a domain you have verified. Resend's free plan allows 100 emails a day and 3,000 a month.

1. Buy or use the domain `finlitventures.com`. You need access to its DNS settings at your domain registrar.
2. Open https://resend.com, **Sign up**, then **Domains**, **Add Domain**, enter `finlitventures.com`.
3. Resend shows a few DNS records (names and values). Add each one in your registrar's DNS page exactly as shown, then click **Verify DNS Records** in Resend. It can take from a few minutes to a day. The domain must show **Verified**.
4. In Resend open **API Keys**, **Create API Key**, permission **Sending access**, copy the key (it is shown once).
5. In Render, **Environment**, add or change: `MAIL_MODE` = `resend`, `RESEND_API_KEY` = the key, `MAIL_FROM` = `FinLit <hello@finlitventures.com>`, `SENDER_EMAIL` = `hello@finlitventures.com`, `CONTACT_RECIPIENT_EMAIL` = the address where contact forms should arrive. Delete `AUTO_VERIFY_EMAIL` only if you want new members to confirm their email address first. Save.

**What you should see:** "Forgot your password?" now sends a real reset link, and the contact form delivers to your recipient address. If you removed `AUTO_VERIFY_EMAIL`, creating an account shows "Check your email" and the confirmation link arrives from your domain.

## Step 11. Move to finlitventures.com after sign-off

Do this only when the company has approved the site. Everything before it works on the Render address.

1. In Render open the service, **Settings**, **Custom Domains**, **Add Custom Domain**. Add `finlitventures.com`, then add `www.finlitventures.com` the same way.
2. Render shows the DNS records to add. Add them in your registrar's DNS page exactly as shown, then click **Verify** in Render. Render issues the secure certificate by itself; wait until it says **Certificate issued**.
3. In Render, **Environment**, set these values and **Save Changes**:

| Name | Value |
| --- | --- |
| `ENVIRONMENT` | `production` |
| `PUBLIC_SITE_URL` | `https://finlitventures.com` |
| `CORS_ORIGINS` | `https://finlitventures.com,https://www.finlitventures.com` |
| `ALLOWED_HOSTS` | `finlitventures.com,www.finlitventures.com,finlit-xxxx.onrender.com` |
| `MAIL_MODE`, `RESEND_API_KEY`, `MAIL_FROM` | As in Step 10 |

Keep your Render address (for example `finlit-xxxx.onrender.com`, without https://) at the end of `ALLOWED_HOSTS`: Render's health checks and the keep-awake pings use it.

4. Delete `AUTO_VERIFY_EMAIL`, `DEMO_PASSWORD` and `ADMIN_PASSWORD`. In `/console` set the three demo accounts to Disabled.
5. Tell the engineer who maintains the repository when you reach this step: the lines `ENVIRONMENT` and `AUTO_VERIFY_EMAIL` in `render.yaml` need changing too, so that Render does not put the old values back at its next sync.

Production mode refuses to start unless every setting is safe. If the service does not come up, open **Logs**: the first line says `Unsafe production configuration:` followed by exactly what is wrong.

**What you should see:** `https://finlitventures.com` shows the same site with a padlock, and sign-up sends real confirmation emails.

## Rotating the FinEdge key later

1. In your FinEdge dashboard create a new key and revoke the old one.
2. In Render open the service, **Environment**, click `FINEDGE_API_KEY`, paste the new key, **Save Changes**.
3. Render redeploys in about 2 minutes. Open the Screener: companies keep loading.
4. Never paste a key into a chat, an email or a file in the repository.

## If something goes wrong

Open the service in Render and read the **Logs** tab first. Lines starting with `[site-api]` come from the blog back end.

| What you see | Likely cause | What to do |
| --- | --- | --- |
| The build fails | A typo or a temporary download problem | Click **Manual Deploy**, **Deploy latest commit**. If it fails again, read the last 30 lines of the log, delete anything that looks like a password, key or web address starting with `postgresql://`, `mongodb`, or `redis://`, then send the rest to the engineer |
| The site shows a spinner or an error for a minute | The free service was asleep | Wait 60 seconds and reload. Step 7 prevents this |
| The Screener is empty | The company load has not run yet, or `DATABASE_URL` is wrong | Wait 5 minutes. In Logs look for a database error. Re-copy the Neon string with pooling OFF |
| Database errors mentioning `-pooler` or prepared statements | The pooled Neon string was used | Use the direct string (Step 1, pooling OFF) |
| Blog, portfolio or forms are empty, or Logs show Mongo errors | `MONGO_URL` is wrong or Atlas does not allow `0.0.0.0/0` | Re-check Step 2 items 3, 4 and 6 |
| `/admin` sends you to Account, Security | The authenticator app is not set up yet | Finish Step 6 |
| The server answers `cms_not_configured` | `CMS_JWT_SECRET` is missing or shorter than 32 characters | Add it in Environment and save |
| Administrator sign-in refused | Wrong password, or the password contains your email name | Set a new `ADMIN_PASSWORD` in Environment and redeploy, then sign in again |
| The chat says it is unavailable | No `GEMINI_API_KEY`, or the free daily limit was reached, or the key was deleted | Step 9. If the limit was reached, wait until it resets (midnight Pacific time) |
| Company data stops updating | Render suspended the service for the month, or FinEdge limits were reached | Check the Render dashboard banner. Only one free service may run in the workspace |
| Neon says the compute allowance is used | Background jobs kept the database awake | In Render Environment add `QUOTES_EVERY_MINUTES` = `10`, and look at the Neon usage page |

## What needs a person (cannot be done by the software)

| What | Who | When |
| --- | --- | --- |
| Rotate the FinEdge key (the old key was exposed) | You, in the FinEdge dashboard and Render | Before launch |
| Create the Neon, MongoDB Atlas and Render accounts and paste the values | You | Steps 1 to 4 |
| Buy the domain and verify it with Resend (DNS records) | You, with the registrar | After sign-off |
| Legal review of the Terms, Privacy notice and research disclosures | The company's legal adviser | Before launch |
| Payments (Razorpay or similar) | The company and an engineer: not built yet. Until then an administrator grants plans in `/console` after a member requests one | When the company decides |
| Add a line to the Privacy notice that chat messages may be processed by Google (free tier: used to improve Google products) | The company's legal adviser | Before launch |
| Weekly backup (Step 8) | You | Every week |
| Refresh the Upstox token, if the ticker is wanted | Whoever owns the Upstox account | Daily |
