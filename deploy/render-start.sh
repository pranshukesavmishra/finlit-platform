#!/usr/bin/env bash
# Container entrypoint for the free single-service deployment (render.yaml).
# Migrates, creates the demo and administrator accounts, starts the site backend and the background jobs, then runs the research API + website.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "${APP_DIR:-/app}"
PY="${PYTHON:-python}"
export PUBLIC_SITE_URL="${PUBLIC_SITE_URL:-${RENDER_EXTERNAL_URL:-http://localhost:8000}}"
export CORS_ORIGINS="${CORS_ORIGINS:-$PUBLIC_SITE_URL}"
# The site backend (blog/CMS, portfolio, forms, chat) runs inside this container, on 127.0.0.1:8001, and the research API forwards to it.
# An explicit SITE_API_URL (a separately hosted site backend) wins. Without MONGO_URL the site backend is not started and those pages show empty states.
SITE_DIR="${SITE_API_DIR:-/app/site-api/backend}"; SITE_PY="${SITE_PYTHON:-/opt/site-venv/bin/python}"
if [ -z "${SITE_API_URL:-}" ] && [ -n "${MONGO_URL:-}" ] && [ -d "$SITE_DIR" ]; then
  export SITE_API_URL="http://127.0.0.1:8001" DB_NAME="${DB_NAME:-finlit}"
  ( cd "$SITE_DIR" && while true; do
      if [ "${SITE_API_DEV:-}" = "1" ]; then   # local testing only: in-memory MongoDB stand-in (see dev/site_api_dev.py)
        "$SITE_PY" "$HERE/../dev/site_api_dev.py" --backend "$SITE_DIR" --port 8001 2>&1 | sed -u "s/^/[site-api] /"
      else
        MALLOC_ARENA_MAX=2 "$SITE_PY" -m uvicorn server:app --host 127.0.0.1 --port 8001 --workers 1 --no-server-header 2>&1 | sed -u "s/^/[site-api] /"
      fi
      echo "[site-api] stopped; restarting in 3 s"; sleep 3
    done ) &
fi
export CLIENT_IP_HEADER="${CLIENT_IP_HEADER:-x-forwarded-for}"

until $PY -m finlit.worker migrate; do echo "waiting for the database..."; sleep 3; done

# Demo members on every plan, so each tier can be shown without waiting for a confirmation email.
if [ -n "${DEMO_PASSWORD:-}" ]; then
  for plan in basic silver gold; do
    FINLIT_MEMBER_PASSWORD="$DEMO_PASSWORD" $PY -m finlit.auth.cli create-member --email "demo-$plan@finlit-demo.com" --plan "$plan" --name "Demo $plan" || true
  done
fi

# The real administrator (ADMIN_EMAIL and ADMIN_PASSWORD in the service's environment). The account is created at the first start. Later starts
# leave the password alone while ADMIN_PASSWORD keeps the same value, so a password changed under Account is kept; typing a NEW value into
# ADMIN_PASSWORD makes it the password at the next start and signs every session out (the way back in without a shell).
# The first sign-in then asks for an authenticator app; admin tools stay closed until it is set up.
if [ -n "${ADMIN_EMAIL:-}" ] && [ -n "${ADMIN_PASSWORD:-}" ]; then
  FINLIT_ADMIN_PASSWORD="$ADMIN_PASSWORD" $PY -m finlit.auth.cli create-admin --email "$ADMIN_EMAIL" || true
fi

# Lost or handed-over authenticator (the free plan has no shell): set RESET_MFA_EMAIL to that account's email, save, and after the restart
# its two-step sign-in is cleared (the next sign-in sets up a new authenticator). Then DELETE the variable.
if [ -n "${RESET_MFA_EMAIL:-}" ]; then
  $PY -m finlit.auth.cli reset-mfa --email "$RESET_MFA_EMAIL" || true
fi

# Company data and the recurring jobs (quotes, nightly refresh, alerts, emails): see deploy/scheduler.sh
export APP_DIR="$PWD" PYTHON="$PY"
# The scheduler's lines go to the file and, prefixed, to the service log, so a job that fails is visible in the Render dashboard.
nohup bash -c "\"$HERE/scheduler.sh\" 2>&1 | tee -a /tmp/scheduler.log | sed -u 's/^/[scheduler] /'" &

exec $PY -m uvicorn --factory finlit.api:create_app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --no-access-log --no-server-header
