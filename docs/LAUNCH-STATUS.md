# Launch status (working notes: read this first when resuming)

Branch `claude/brave-mayer-fkr9oj`; push to `main` only after the checks below pass. Rules: everything free, no secrets in chat or git, one small step per instruction to the user.

## Architecture (decided)
One free Render web service = website + research API (backend/) + the company site backend (site-api/backend, MongoDB) + scheduler (deploy/scheduler.sh). Postgres = Neon (external, DATABASE_URL by hand), Redis = Render free keyvalue, MongoDB = Atlas M0. Reason: Render free = 750 instance hours per workspace and free services cannot receive private-network traffic. render.yaml, Dockerfile, deploy/render-start.sh.

## Verified by running (local, clean databases)
- backend pytest 136, site-api pytest 52 (1 skipped), tsc clean
- e2e: accounts 85/85 (needs `SHOWCASE_SYMBOLS=NONE dev/run_stack.sh`), tools 34/34 + alerts 19/19 (demo build, VITE_DEMO=1, served like GitHub Pages), smoke 24/24 (default showcase, DEMO_PASSWORD), deploy_check (single-container start script), score_screener, sweep, mobile 390px
- backup round trip (scripts/backup.sh then decrypt then pg_restore): same rows

## Fixed in this pass
render loop that froze nav/sign-in tabs; CSRF token timing (admin landed on wrong page); admin token request loop + clear messages (cms_not_configured / secret mismatch); free-example company no longer locked by the UI (`showcase` in /api/auth/me + OpenAccess in Gate); queue worker no longer polls Postgres (Neon can sleep); /api/ping; GEMINI_MODEL setting; stale e2e scripts updated (smoke, deploy_check, sweep).

## Not yet done (brief items 3-9)
- verify Neon-specific behaviour is only by unit tests (no Neon account here); Docker image never built here (no daemon)
- forms/contact save check without email, data-health page review, loading states, security headers/gitleaks/pip-audit pass, robots/sitemap/404/titles/a11y spot checks
- guide: docs/LAUNCH-GUIDE.md + PDF (docs/FinLit-Launch-Guide.pdf) must be updated: email/login wording, Gemini steps (free tier: Gemini 3.8 Flash is free of charge, but free-tier content may be used by Google to improve products)
- independent audit sub-agent, fix findings, second pass; final report

## Gotchas when testing
- killing the site backend alone does not help: deploy/render-start.sh respawns it; `pkill -f "[r]ender-start.sh"` first
- never put the pkill pattern text elsewhere in the same shell command (it kills its own shell)
