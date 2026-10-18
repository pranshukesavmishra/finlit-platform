# Master prompt for the "FinLit platform setup and validation" chat

Paste everything inside the box into that chat.

```
You are taking this project to launch. The user's job depends on it, so be thorough, honest and verify everything yourself. Do not say something works until you have run it. Tell me plainly what fails.

REPO AND RULES
- Repo: pranshukesavmishra/finlit-platform. Work on a branch, merge origin/main first (it contains the latest website work), then push to main when checks pass. Never deploy to the "simpdash" repo.
- Everything must be FREE. No paid plans. The user is a junior employee paying nothing; the only future cost is a domain after sign-off.
- Never ask the user to paste a secret (FinEdge key, passwords, tokens) into chat. Secrets go only into the Render / GitHub / Neon dashboards. Tell the user exactly where.
- The FinEdge API key was exposed earlier; it will be rotated by the user later. Never print it, never commit it.
- The user knows little about servers. Every instruction you give them must be one small step with exact clicks and what they should see after it.

GOAL
One fully working, end-to-end company website for FinLit Ventures, on the free Render address now (finlitventures.com later). Frontend, backend, databases, login, plans, admin, alerts, blog/CMS, forms, chat, background jobs, all connected and tested. The company will only approve launch if all of it works.

WHAT ALREADY EXISTS (verify, do not assume)
- Website: React + TypeScript in frontend/. Pages: Home (hero, platform, services, why, pricing, results, process, founder, FAQ), Services, Plans/Pricing, About, Why we exist, Contact, Blog, Portfolio (track record), Glossary, Legal (terms, privacy, disclosures), one sign-in page /login (sign in + create account + forgot/reset password + email verification), account pages, dashboard with first-login checklist, stock research for every listed company, screener, compare, watchlists, portfolio tracker, alerts + notification bell, results calendar, IPO calendar, news and filings, documents, admin console (members, plan requests, calendar and news content, data health, audit log), CMS (blog and enquiries) at /admin with NO second password for signed-in admins (token from POST /api/me/cms-token; needs the same CMS_JWT_SECRET on both services).
- Research and accounts API: backend/ (FastAPI, Postgres, Redis, argon2 passwords, sessions, CSRF, rate limits, two-step login for admins, plan gating on the server, alerts engine, worker jobs). Migrations 001-011.
- Company site backend (blog/CMS, portfolio report, contact and enquiry forms, FinLit AI chat, ticker): the Financial-Portfolio code (vendored in the repo as site-api, also uploaded as a zip by the user: Financial-Portfolio-main.zip). Uses MongoDB.
- Deploy: Dockerfile + render.yaml (one container: website + API + background scheduler), deploy/ (Caddy, compose, crontab, scheduler.sh), docs/ (deploy-free.md, LAUNCH-RUNBOOK.md, accounts-and-plans.md), tests (pytest 127 tests; frontend/e2e/accounts.mjs, alerts.mjs, tools.mjs, deploy_check.mjs, sweep.mjs).
- Plans: Basic (free), Silver, Gold, enforced on the server. Payments are not integrated yet: the team grants plans from the admin console (plan requests).

DO ALL OF THIS, IN ORDER

1. AUDIT FIRST. Read the repo and the zip. Produce a short checklist of every page, button, form and API route a visitor, a member and an admin can reach. Run the full stack locally (dev/run_stack.sh, with SHOWCASE_SYMBOLS=NONE for the accounts test) and the whole test suite. List what fails.

2. FIX EVERYTHING THAT FAILS, then re-run. Pay special attention to: sign-up -> verification link -> sign-in -> dashboard; wrong password; lockout; forgot/reset password; sign-out; session cookie on the Render address (cookies must work without a custom domain: COOKIE_SAMESITE setting) ; admin sign-in -> two-step setup -> console -> /admin CMS with no second login; plan request -> admin grants -> member sees Silver/Gold features without signing in again; Basic members never receive Silver/Gold data from the API.

3. FREE DATABASES THAT DO NOT EXPIRE. Render's free Postgres is deleted after 30 days. Use a free Neon Postgres for DATABASE_URL (migrations must run on plain Postgres without Timescale), free Redis (Render free or Upstash), free MongoDB Atlas M0 for the site backend. Give the user exact sign-up and connection-string steps for each.

4. FREE HOSTING THAT STAYS AWAKE. Render free gives about 750 instance hours per month per workspace, shared by services. Run the site backend inside the same container as the main service if feasible so only one service runs; otherwise ping both only 09:00-21:00 IST. Add a keep-awake job (GitHub Actions) and an optional UptimeRobot monitor. Verify the current free-tier limits against Render's own documentation before you state numbers.

5. EMAIL. Real email needs a verified domain. For the demo: keep demo members (demo-basic, demo-silver, demo-gold), add an admin action to confirm a member's email by hand if there is none, and make Resend setup a clearly marked later step. Contact and enquiry forms must still save messages for the admin even without email.

6. DATA. Companies load in the background from FinEdge (INGEST_LIMIT). Make sure the search, screener, stock pages, results/IPO/news calendars and dashboard show real data once loaded and a friendly state while loading. Add a data-health check the admin can read.

7. SECURITY AND LAUNCH HYGIENE. Production mode checks, security headers, rate limits, no secrets in git (gitleaks), dependency audit, backups (weekly pg_dump of Neon + MongoDB Atlas export, where to keep them), privacy/terms pages present, robots/sitemap, 404 page, mobile layouts at 390px, accessibility basics, page titles.

8. LAUNCH GUIDE FOR THE USER. One document (docs/ and an artifact), one step per heading, in order: accounts to create (GitHub, MongoDB Atlas, Neon, Render, optional Resend, Google AI Studio for chat, UptimeRobot) with exact clicks; every environment variable in a table (name, what it is, where to get it, who sets it); first logins for each account type; how to rotate the FinEdge key later; how to add finlitventures.com and switch to production mode later; a "something went wrong" table (symptom -> fix); a "what costs money and when" table showing 0 today; and a short "what works / what needs a person" list for the company meeting.

9. INDEPENDENT VERIFICATION AGENT. When you think everything is done, start a separate sub-agent (fresh context, it must not trust your claims) with this brief: "You are an auditor. Clone the repo main branch. Run the full stack and every test and e2e script. Crawl every route at 1366px and 390px width and report console errors, failed requests and broken layouts. Walk the launch guide step by step as a non-technical person and list every step that is missing, ambiguous or wrong. Try to break security: access admin and Silver/Gold data as a visitor and as a Basic member, try CSRF, try weak passwords, try wrong codes. Report findings as a numbered list with severity and proof." Fix everything it finds, then run a second audit pass until it reports nothing serious.

10. FINAL REPORT. Short and honest: what was verified and how, what still needs a human (rotating the key, verifying a domain, legal review, payment gateway), and the exact next three actions for the user.

Keep the user informed in plain language after each step. If you are blocked on something only the user can do (creating an account, clicking a button in a dashboard), stop and give them that one step, nothing else.
```
