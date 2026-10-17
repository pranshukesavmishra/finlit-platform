#!/usr/bin/env bash
# Container entrypoint for the free single-service deployment (render.yaml).
# Migrates, creates the demo accounts, loads company data in the background (resumable), then runs the API + website.
set -uo pipefail
cd "${APP_DIR:-/app}"
PY="${PYTHON:-python}"
export PUBLIC_SITE_URL="${PUBLIC_SITE_URL:-${RENDER_EXTERNAL_URL:-http://localhost:8000}}"
export CORS_ORIGINS="${CORS_ORIGINS:-$PUBLIC_SITE_URL}"
export CLIENT_IP_HEADER="${CLIENT_IP_HEADER:-x-forwarded-for}"

until $PY -m finlit.worker migrate; do echo "waiting for the database..."; sleep 3; done

# Demo members on every plan, so each tier can be shown without waiting for a confirmation email.
if [ -n "${DEMO_PASSWORD:-}" ]; then
  for plan in basic silver gold; do
    FINLIT_MEMBER_PASSWORD="$DEMO_PASSWORD" $PY -m finlit.auth.cli create-member --email "demo-$plan@finlit-demo.com" --plan "$plan" --name "Demo $plan" || true
  done
fi

# Company data: the universe first (names, sectors), then full reports for as many companies as INGEST_LIMIT allows.
(
  $PY -m finlit.worker refresh-universe && \
  $PY -m finlit.worker ingest RELIANCE TCS INFY HDFCBANK ICICIBANK SBIN ITC LT BHARTIARTL HINDUNILVR && \
  $PY -m finlit.worker ingest-all --limit "${INGEST_LIMIT:-1500}" --parallel 2
) > /tmp/ingest.log 2>&1 &

exec $PY -m uvicorn --factory finlit.api:create_app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --no-access-log --no-server-header
