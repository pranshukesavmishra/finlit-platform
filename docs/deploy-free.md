# Free end-to-end deployment (website + API + database), about 15 minutes

Everything runs as **one Render service** (website and API on the same address, so there are no cookie or CORS problems) with Render's free Postgres and Redis.
The repository already contains what Render needs: `render.yaml`, `Dockerfile`, `deploy/render-start.sh`.

## Steps
1. Create a free account at https://render.com ("Sign in with GitHub"), and allow it to read `pranshukesavmishra/finlit-platform`.
2. **New → Blueprint →** choose the repository (branch `main`) → **Apply**. Render builds the image (about 5–8 minutes) and creates the database and Redis.
3. When it asks for `FINEDGE_API_KEY`, paste the FinEdge key. (It lives only in Render's settings; it is never written to the repository.)
4. Open the service → **Environment** → copy `DEMO_PASSWORD`. The demo accounts (confirmed, no email needed) are
   `demo-basic@finlit-demo.com`, `demo-silver@finlit-demo.com`, `demo-gold@finlit-demo.com`.
5. Open the service URL (`https://finlit-xxxx.onrender.com`). Companies appear in the background: about 60 a minute after the first start (the first 10 large companies within a minute or two).

## Before the meeting
- Free services sleep after 15 minutes idle and take about a minute to wake. Open the site 5 minutes before, or set the repository variable `SITE_URL` to the service URL: the workflow *Keep the free server awake* then pings it every 10 minutes.
- Check everything in one command: `cd frontend && DEMO_PASSWORD=... node e2e/deploy_check.mjs https://finlit-xxxx.onrender.com` (needs Playwright). It signs in as the demo members and checks the main pages and the plan rules.
- The free Postgres expires after 30 days. For anything longer use the VPS route in `deploy/README.md`.

## Known limits of this free setup
- `ENVIRONMENT=staging`: sign-up emails are not sent (they go to the `outbox` table), which is why the demo accounts exist. Real email needs a verified domain and `MAIL_MODE=resend`.
- The blog/CMS, portfolio report and the top market ticker come from the older site backend (a separate codebase). Until it is deployed too, those three show empty states.
- Only `INGEST_LIMIT` companies (default 1500) are loaded after each start, NSE tickers first; raise it in the service's Environment tab.
