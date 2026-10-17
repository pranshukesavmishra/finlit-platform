#!/usr/bin/env bash
# Container entrypoint for the free single-service deployment (render.yaml).
# Migrates, creates the demo accounts, loads company data in the background (resumable), then runs the API + website.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
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

# The real administrator (set ADMIN_EMAIL and ADMIN_PASSWORD in the service's environment; they are applied at every start).
# The first sign-in then asks for an authenticator app; admin tools stay closed until it is set up.
if [ -n "${ADMIN_EMAIL:-}" ] && [ -n "${ADMIN_PASSWORD:-}" ]; then
  FINLIT_ADMIN_PASSWORD="$ADMIN_PASSWORD" $PY -m finlit.auth.cli create-admin --email "$ADMIN_EMAIL" || true
fi

# Company data and the recurring jobs (quotes, nightly refresh, alerts, emails): see deploy/scheduler.sh
export APP_DIR="$PWD" PYTHON="$PY"
nohup "$HERE/scheduler.sh" >> /tmp/scheduler.log 2>&1 &

exec $PY -m uvicorn --factory finlit.api:create_app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --no-access-log --no-server-header
