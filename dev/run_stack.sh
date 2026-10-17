#!/usr/bin/env bash
# Local full stack for development and end-to-end tests: Postgres + Redis, research/accounts API (8000), the older site API (8001),
# and the website build served on 4173 with /api proxied to both. Needs: postgres, redis-server, the backend venv, node.
# Set SITE_PY (a python with the old site backend's requirements + mongomock-motor) and SITE_BACKEND (its backend folder).
# Mail goes to the `outbox` table (MAIL_MODE=console); FinEdge runs from recorded fixtures. Stop with: dev/run_stack.sh stop
# LIVE_DATA=1 dev/run_stack.sh: use the real FinEdge key from the environment and the companies already loaded with
#   `python -m finlit.worker ingest-all`; no fixtures and no fictional SMP- companies. SITE_BACKEND is then optional.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="${STACK_LOG:-/tmp/finlit-stack}"; mkdir -p "$LOG"
export DATABASE_URL="${DATABASE_URL:-postgresql://finlit:finlit@localhost:5432/finlit_dev}" REDIS_URL="${REDIS_URL:-redis://localhost:6379/14}"
export ENVIRONMENT=development MAIL_MODE=console PUBLIC_SITE_URL="http://localhost:4173"
if [ "${LIVE_DATA:-}" = "1" ]; then
  : "${FINEDGE_API_KEY:?LIVE_DATA=1 needs FINEDGE_API_KEY in the environment}"; export FINEDGE_MODE=live
else
  export FINEDGE_MODE=fixtures FINEDGE_API_KEY=dev
fi
export CORS_ORIGINS="http://localhost:4173,http://127.0.0.1:4173,http://localhost:5173" RATE_LIMIT_PER_MINUTE=100000

if [ "${1:-}" = "stop" ]; then pkill -f "[f]inlit.api:create_app" || true; pkill -f "[s]ite_api_dev" || true; pkill -f "[v]ite preview" || true; exit 0; fi

cd "$ROOT/backend"; PY=.venv/bin/python
$PY -m finlit.worker migrate
if [ "${LIVE_DATA:-}" != "1" ]; then
  $PY -m finlit.worker refresh-universe >/dev/null
  $PY -m finlit.worker ingest RELIANCE >/dev/null
  $PY scripts/seed_dev_universe.py ../frontend/public/demo/screener.json
fi
nohup $PY -m uvicorn --factory finlit.api:create_app --port 8000 >"$LOG/research.log" 2>&1 &
cd "$ROOT"
if [ -n "${SITE_BACKEND:-}" ] || [ "${LIVE_DATA:-}" != "1" ]; then
  nohup "${SITE_PY:-python3}" dev/site_api_dev.py --backend "${SITE_BACKEND:?set SITE_BACKEND to the Financial-Portfolio/backend folder}" --port 8001 >"$LOG/site.log" 2>&1 &
fi
cd "$ROOT/frontend"; VITE_BASE=/ npx vite build >"$LOG/build.log" 2>&1
nohup npx vite preview --port 4173 --strictPort >"$LOG/preview.log" 2>&1 &
sleep 4; echo "stack up: http://localhost:4173  (logs in $LOG)"
