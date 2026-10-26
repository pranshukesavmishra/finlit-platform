#!/usr/bin/env bash
# Container entrypoint for the free single-service deployment (render.yaml).
# Migrates, creates the demo and administrator accounts, starts the site backend and the background jobs, then runs the research API + website.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "${APP_DIR:-/app}"
PY="${PYTHON:-python}"
export PUBLIC_SITE_URL="${PUBLIC_SITE_URL:-${RENDER_EXTERNAL_URL:-http://localhost:8000}}"
export CORS_ORIGINS="${CORS_ORIGINS:-$PUBLIC_SITE_URL}"
# The site backend (blog/CMS, portfolio, forms, chat, FinLit Prism reports, Gold market data) runs inside this container, on
# 127.0.0.1:8001, and the research API forwards to it. An explicit SITE_API_URL (a separately hosted site backend) wins.
# It starts when MONGO_URL is set, or when FinLit Prism can work without it: FINEDGE_API_KEY and a CMS_JWT_SECRET of 32+ characters
# (the blog/CMS and forms then answer "not connected" and the blog index stays empty). SITE_API_START=never keeps it off
# (saves about 90 MB; Prism and the Gold market pages then say "not connected"); SITE_API_START=always starts it regardless.
# See docs/prism/DEPLOY.md.
SITE_DIR="${SITE_API_DIR:-/app/site-api/backend}"; SITE_PY="${SITE_PYTHON:-/opt/site-venv/bin/python}"
site_api_wanted() {
  case "${SITE_API_START:-auto}" in
    never|off|0) echo "[site-api] not started: SITE_API_START=${SITE_API_START}"; return 1 ;;
    always|on|1) return 0 ;;
  esac
  local secret="${CMS_JWT_SECRET:-}"
  if [ -n "$secret" ] && [ "${#secret}" -lt 32 ]; then
    echo "[site-api] CMS_JWT_SECRET is shorter than 32 characters: FinLit Prism and the CMS admin stay off until it is longer" >&2
  fi
  if [ -n "${MONGO_URL:-}" ]; then echo "[site-api] starting (MongoDB configured)"; return 0; fi
  if [ -n "${FINEDGE_API_KEY:-}" ] && [ "${FINEDGE_MODE:-live}" != "fixtures" ] && [ "${#secret}" -ge 32 ]; then
    echo "[site-api] starting without MongoDB: FinLit Prism and market data on; blog/CMS, portfolio uploads and forms off (set MONGO_URL for those)"
    return 0
  fi
  echo "[site-api] not started: needs MONGO_URL, or FINEDGE_API_KEY + CMS_JWT_SECRET (32+ characters) for FinLit Prism"
  return 1
}
if [ -z "${SITE_API_URL:-}" ] && [ -d "$SITE_DIR" ] && site_api_wanted; then
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
# Indian dates everywhere: the jobs already run on IST (scheduler.sh); the API must agree, or "today" is yesterday between midnight and 05:30 IST.
export TZ="${TZ:-Asia/Kolkata}"

# Retries for a database that is still waking up, but gives up after ~5 minutes so a migration that really fails shows as a failed deploy.
tries=0
until $PY -m finlit.worker migrate; do
  tries=$((tries + 1))
  if [ "$tries" -ge 100 ]; then echo "migrate still failing after $tries attempts: giving up" >&2; exit 1; fi
  echo "waiting for the database (attempt $tries)..."; sleep 3
done

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

# glibc keeps one memory arena per thread by default: two arenas cut the web server's and every job's memory noticeably on the 512 MB free plan
export MALLOC_ARENA_MAX="${MALLOC_ARENA_MAX:-2}"
exec $PY -m uvicorn --factory finlit.api:create_app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --no-access-log --no-server-header
