#!/usr/bin/env bash
# Run before ANY push to main:  bash scripts/preflight.sh      (needs `bash dev/services.sh` once for Postgres and Redis)
# Runs every check, keeps going after a failure, prints a one-line summary per step, and exits non-zero if any step failed.
# Env: SKIP_BACKEND=1 / SKIP_FRONTEND=1 skip a half; GITLEAKS=/path/to/gitleaks; TEST_DATABASE_URL / TEST_REDIS_URL override the defaults below.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
LOG="$(mktemp -d)"; trap 'rm -rf "$LOG"' EXIT
RESULTS=(); FAILED=0
PY="$ROOT/backend/.venv/bin/python"; [ -x "$PY" ] || PY="$(command -v python3)"
export TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql://finlit:finlit@localhost:5432/finlit_test}" TEST_REDIS_URL="${TEST_REDIS_URL:-redis://localhost:6379/15}"

step() {  # step <name> <command...>: output kept in $LOG/<name>, shown only when the step fails
  local name="$1"; shift
  if "$@" >"$LOG/$name" 2>&1; then RESULTS+=("PASS  $name"); else RESULTS+=("FAIL  $name"); FAILED=$((FAILED + 1)); echo "---- $name failed (last 25 lines)"; tail -n 25 "$LOG/$name"; fi
}
skip() { RESULTS+=("SKIP  $1 ($2)"); }

if [ -z "${SKIP_BACKEND:-}" ]; then
  step backend-pytest bash -c "cd backend && PYTHONPATH=. '$PY' -m pytest -q"
  if "$PY" -c "import motor, mongomock_motor" >/dev/null 2>&1; then
    step site-api-pytest bash -c "PYTHONPATH=.:backend '$PY' -m pytest -q -c site-api/backend/pytest.ini site-api/backend/tests"
  else skip site-api-pytest "site-api dependencies not installed; CI runs it"; fi
  if command -v bandit >/dev/null 2>&1; then step bandit bandit -q -r backend/finlit -ll
  else step bandit "$PY" -m bandit -q -r backend/finlit -ll; fi
fi

if [ -z "${SKIP_FRONTEND:-}" ]; then
  # `three` missing = the sandbox; only then is the src/three error filtered. Any other tsc error fails.
  if [ -d frontend/node_modules/three ]; then step tsc bash -c "cd frontend && npx tsc --noEmit"
  else step tsc bash -c "cd frontend && ! npx tsc --noEmit | grep -v 'src/three' | grep -E 'error TS'"; fi
  step vitest bash -c "cd frontend && npx vitest run"
  step build bash -c "cd frontend && npm run build"
fi

step shell-syntax bash -c 'for f in deploy/*.sh scripts/*.sh dev/*.sh; do [ -f "$f" ] || continue; bash -n "$f" || exit 1; done'

GL="${GITLEAKS:-$(command -v gitleaks || true)}"
if [ -n "$GL" ] && [ -x "$GL" ]; then step gitleaks "$GL" git --redact --no-banner .; else skip gitleaks "not installed: set GITLEAKS=/path/to/gitleaks"; fi

secret_scan() {  # patterns of real secrets in tracked and new files (never prints the secret itself)
  local files
  files="$(git ls-files -co --exclude-standard | grep -vE '\.(png|jpg|jpeg|gif|ico|pdf|woff2?|gz|lock)$|^scripts/preflight\.sh$|^frontend/package-lock\.json$')"
  : > "$LOG/scan"
  for p in 'AKIA[0-9A-Z]{16}' '-----BEGIN ([A-Z]+ )?PRIVATE KEY-----' 'gh[pousr]_[A-Za-z0-9]{36,}' 'sk-[A-Za-z0-9_-]{32,}' 'xox[baprs]-[A-Za-z0-9-]{20,}' 'AIza[0-9A-Za-z_-]{35}'; do
    echo "$files" | xargs -d '\n' grep -lEI -e "$p" 2>/dev/null | head -3 | sed "s|^|secret-like text (pattern $p) in: |" >> "$LOG/scan"
  done
  for k in FINEDGE_API_KEY RESEND_API_KEY DHAN_ACCESS_TOKEN; do   # the real values from this environment, if set
    v="${!k:-}"; [ "${#v}" -ge 12 ] && echo "$files" | xargs -d '\n' grep -lF -e "$v" 2>/dev/null | sed "s|^|value of $k found in: |" >> "$LOG/scan"
  done
  [ ! -s "$LOG/scan" ] || { cat "$LOG/scan"; return 1; }
}
step secret-scan secret_scan

echo; echo "==== preflight summary"
printf '%s\n' "${RESULTS[@]}"
if [ "$FAILED" -gt 0 ]; then echo "PREFLIGHT FAILED: $FAILED step(s). Do not push."; exit 1; fi
echo "PREFLIGHT OK"
