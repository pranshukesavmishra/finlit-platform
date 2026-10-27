# Handover prompt for a new Claude session (paste it as the first message)

You are taking over an ongoing project from another Claude session that ran out of weekly limit. Read this fully, then read the repo docs named below, then continue. I am Pranshu, founder of FinLit Ventures. I write in English/Hinglish. Keep answers short.

## How to work with me (strict)
- Give me ONE step at a time (at most 2-3 tiny ones), minimal explanation, and ask for a screenshot. I run commands on my Windows PC (PowerShell) and on the server myself; you cannot reach the server.
- Accuracy is the top rule: numbers must be right, and never missing when data exists. A wrong or missing number hurts the company's image. State limits honestly; never guess.
- Compliance wording: never show buy / sell / hold / reduce / avoid / accumulate / target language. Keep the line "Describes the company's financial health from its filings and prices; not a recommendation."
- Everything must stay free. Secrets (API keys, passwords, tokens) only in the server's `/opt/finlit/.env.aws` or dashboards; NEVER in chat or in the repo.
- Push to `main` ONLY when I say "push to main". Work on the branch below. Never open a PR unless I ask.
- Take decisions yourself, use sub-agents for big builds, test everything (and look at screenshots of UI), and verify what an agent reports before trusting it.

## Repos
- Personal repo `pranshukesavmishra/finlit-platform`, work branch `claude/brave-mayer-fkr9oj` (everything below is pushed there; `main` is the old Render deployment). Add it with add_repo if it is not in the session.
- Company repo `Yusra-Khan532/Financial-Portfolio`: its `main` contains our project in the folder `finlit-platform/` (merged by Yusra as PR #41). The company will make future changes there. Moving our changes there is done with `scripts/export-to-company.sh` (see `docs/COMPANY-HANDOVER.md`); the Prism model files (`site-api/backend/premium_*.py`) are the company's, so tell them about any change to them.

## What the product is
Indian equity-research site. React+TypeScript frontend (Vite, react-query, vitest); FastAPI research API (`backend/finlit`, Postgres/Timescale, Redis, worker CLI `python -m finlit.worker`); site backend `site-api/backend` (Mongo Atlas, Prism model, FinLit AI chat with Gemini); one Docker image (`Dockerfile`, `deploy/render-start.sh`, scheduler `deploy/scheduler.sh`). Read first: `README.md`, `docs/COMPANY-HANDOVER.md`, `docs/AWS-DEPLOY.md`, `docs/KNOWN-ISSUES.md`, `docs/LAUNCH-STATUS.md`, `docs/prism/CONTRACT.md`.

## Hosting now
- Old: Render free (https://finlit-arug.onrender.com) with Neon free Postgres (its monthly compute quota was exhausted; I have not decided whether to wait for the reset or use a new free Neon project, which would lose member data). Keep Render running until AWS is fully tested.
- New: AWS EC2 (Free plan, region Sydney, Ubuntu 24.04, t3.small, 20 GiB), Elastic IP `54.253.190.17`, plain http for now (no domain yet). Docker Compose + Caddy kit in `deploy/aws/`. Postgres and Redis run as containers on the box; MongoDB stays on Atlas.
- Log in: `ssh -o ServerAliveInterval=30 -i $HOME\Downloads\finlit-key.pem ubuntu@54.253.190.17` (the connection drops often; just log in again).
- Server layout: `/opt/finlit/.env.aws` (secrets, never print it), `/opt/finlit/src` (git clone that deploy.sh updates).
- Deploy everything pushed on the branch (run on the server, from `/opt/finlit`):
  `REPO_URL=https://github.com/pranshukesavmishra/finlit-platform.git REPO_BRANCH=claude/brave-mayer-fkr9oj REPO_SUBDIR=. bash src/deploy/aws/deploy.sh`
  The goal is to deploy later from the company repo (defaults in the kit: Yusra's repo, folder `finlit-platform`) once our work is merged there. Other commands: `bash src/deploy/aws/deploy.sh status|logs|rollback|backup`. To run a worker command: `docker compose --env-file .env.aws -f src/deploy/aws/docker-compose.aws.yml exec -T app python -m finlit.worker <cmd>`. When you change `.env.aws`, recreate the app: `docker compose ... up -d --force-recreate app` (with `export ENV_FILE=/opt/finlit/.env.aws`).
- Admin login: jnishant2028@gmail.com at /login. `ADMIN_REQUIRE_MFA=0` for now (team asked); must be set to 1 before a public launch.
- AWS free plan lasts about 6 months (credits $100, about 183 days from 27 Apr 2026 in my account; I must decide before it ends). No payment method is added; never click "Upgrade account". Not yet confirmed: budget alarm and root MFA.

## Done in the last sessions (all on the branch, deployed to AWS at commit e1fea65 unless noted)
Wake-budget/OOM fixes for Render; export to the company repo; AWS kit and server running; December-year companies' yearly ratios fixed (they were being dropped); Prism: automatic calculation when a report opens, always-on background precompute loop (`deploy/scheduler.sh`, two workers via `--shard`), Dhan repeated-day candles collapsed (`prism_candles.collapse_repeats`), a 502 company waits 45 min instead of blocking the queue; PEG is a core factor for banks; earnings-flags popup for banks uses the Revenue line (same as the statements); results page "Detailed view" dropdown; large section numbers (01, 02 ...); Gold insights revenue-segments title larger; per-area pros/cons card removed; Investment calculators group in the left menu; "Formula screener" renamed "Query builder"; advanced Score screener (`/score-screener`, sidebar, apply, chips, presets, CSV, compare); growth filters (QoQ/YoY, AND/OR) with three donut charts on Latest results; score tiles coloured green >=70, orange 50-69, red <50; a public MCP server at `/mcp` (20 read-only tools, `scripts/mcp-check.sh <url>` passes on AWS) and the FinLit AI chatbot now calls those tools; ETF/fund loading switched on (`FUND_LOADS_ENABLED=1`).

## Open items (in priority order)
1. Prism speed (my biggest concern): only part of the companies have a stored rating (200 at last count; check `select count(*) from prism_reports`). A calculation takes about 30 s; a stored rating should open instantly. Measure real latencies (stored vs fresh), watch `/tmp/job-prism-loop.log` in the app container (failures now log their reason, many were 502 for specific companies: find the cause), and tune. Never loosen the data-quality rules to go faster.
2. Check funds and ETFs loaded completely: `http://54.253.190.17/api/mf/status`; no missing values; every blank must show its reason.
3. Test the chatbot live (Ask FinLit AI) with the real Gemini key: it was only tested against a stand-in.
4. Check the new pages in dark theme (not visually checked), and the new Detailed view and screener on live data.
5. Company-name items from my review list that are still open: the Insurance Quality factor (the model already uses financial leverage for insurers; my teammate says it is being handled), plus anything new I send. I send numbered review items with screenshots; handle them one by one, deploy once per batch.
6. Before real launch: `ADMIN_REQUIRE_MFA=1`; a domain name + HTTPS (Caddy `DOMAIN=`); off-box backups (nightly backup stays on the same disk); second admin account for p.m.pranshu.mishra1111@gmail.com; Dhan written permission to show its data publicly; decide Neon/Render fate; confirm AWS budget alarm; decide what happens when the AWS free period ends; install the Claude GitHub App on the company repo or keep using the export script.
7. MCP server has no sign-in (no OAuth): ChatGPT-style clients that require OAuth cannot use it; a token/OAuth version is a later step.

## Tests and tools
- Frontend: `cd frontend && npx vitest run && npx tsc --noEmit` (the missing `three` module errors are known). Backend: `bash dev/services.sh`, then `cd backend && TEST_DATABASE_URL=postgresql://finlit:finlit@localhost:5432/finlit_test TEST_REDIS_URL=redis://localhost:6379/1 PYTHONPATH=. .venv/bin/python -m pytest -q` (3 tests in `test_options.py` fail only because of the date: known). Site backend: `cd site-api/backend && FINEDGE_API_KEY= PYTHONPATH=..:. python -m pytest -q -c pytest.ini .`. Everything before a push: `scripts/preflight.sh`. Live check: `scripts/smoke.sh <url>` and `scripts/mcp-check.sh <url>`.
- Commit messages end with the attribution lines your harness gives you. Do not put model names in commits.

Start by: (1) reading the docs above, (2) telling me in 5 lines what you understood and what you will do first, (3) giving me my first single step.
