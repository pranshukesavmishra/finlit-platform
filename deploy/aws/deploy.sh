#!/usr/bin/env bash
# Deploy / update / roll back / inspect the FinLit stack on THIS server. Run it as the ubuntu user (after bootstrap.sh):
#   bash /opt/finlit/src/finlit-platform/deploy/aws/deploy.sh              pull the latest code from the company repository, rebuild, restart, check health
#   bash .../deploy.sh rollback                                            go back to the previous build
#   bash .../deploy.sh status                                              which commit runs, container health, disk, memory
#   bash .../deploy.sh logs [service]                                      follow the logs (app, db, redis, caddy, backup); Ctrl+C to stop
#   bash .../deploy.sh restart [service]                                   restart one service or all (no rebuild)
#   bash .../deploy.sh backup                                              take a database backup now
#   bash .../deploy.sh restore FILE.dump                                   replace the database with a backup (asks first; file name as listed by "backups")
#   bash .../deploy.sh backups                                             list the backups
#   bash .../deploy.sh compose ARGS...                                     any docker compose command for this stack, e.g. compose ps
#
# Layout (FINLIT_HOME, default /opt/finlit):
#   $FINLIT_HOME/.env.aws        your settings and secrets (never inside the git clone, so a pull never touches it)
#   $FINLIT_HOME/src/            clone of the company repository (REPO_URL, branch REPO_BRANCH)
#   $FINLIT_HOME/src/$REPO_SUBDIR   the folder that holds the Dockerfile: the build context
#   $FINLIT_HOME/state/          small notes: which commit is running
# Private repository: export GIT_TOKEN=<a read-only deploy token> before running (it is handed to git through a throw-away helper,
# never printed, never written to disk or to the repository settings). The default repository is public and needs nothing.
set -Eeuo pipefail

FINLIT_HOME="${FINLIT_HOME:-/opt/finlit}"
REPO_URL="${REPO_URL:-https://github.com/Yusra-Khan532/Financial-Portfolio.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"
REPO_SUBDIR="${REPO_SUBDIR:-finlit-platform}"
SRC="$FINLIT_HOME/src"
PROJ="$SRC/$REPO_SUBDIR"
export ENV_FILE="${ENV_FILE:-$FINLIT_HOME/.env.aws}"
STATE="$FINLIT_HOME/state"
IMAGE=finlit-app
ASKPASS=""
trap '[ -z "$ASKPASS" ] || rm -f "$ASKPASS"' EXIT
HEALTH_WAIT_S="${HEALTH_WAIT_S:-600}"

say()  { printf '\n==> %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
die()  { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# Everything runs inside main(), and the file is only read to the end of the last line: the script replaces itself when git pulls a newer version.
# EXTRA_COMPOSE_FILE and FRONT_HTTP_PORT exist only so the kit can be tested on a machine whose ports 80/443 are taken; leave them unset on the server.
dc() {
  local files=(-f "$PROJ/deploy/aws/docker-compose.aws.yml")
  [ -z "${EXTRA_COMPOSE_FILE:-}" ] || files+=(-f "$EXTRA_COMPOSE_FILE")
  docker compose -p finlit "${files[@]}" --env-file "$ENV_FILE" "$@"
}

envval() {  # envval NAME -> the value in the env file (last assignment wins), surrounding quotes removed; the file is read, never executed
  local v
  v="$(grep -E "^[[:space:]]*$1=" "$ENV_FILE" | tail -n 1 | sed -E "s/^[[:space:]]*$1=//; s/[[:space:]]+$//")" || true
  v="${v%\"}"; v="${v#\"}"; v="${v%\'}"; v="${v#\'}"
  printf '%s' "$v"
}

need_docker() {
  command -v docker >/dev/null || die "docker is not installed: run deploy/aws/bootstrap.sh first."
  docker info >/dev/null 2>&1 || die "docker is not usable by this user. After bootstrap.sh you must log out and log in again (the 'docker' group), then retry."
  docker compose version >/dev/null 2>&1 || die "the docker compose plugin is missing: run bootstrap.sh again."
}

public_ip() {
  local tok ip=""
  tok="$(curl -fsS -m 2 -X PUT -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' http://169.254.169.254/latest/api/token 2>/dev/null || true)"
  [ -n "$tok" ] && ip="$(curl -fsS -m 2 -H "X-aws-ec2-metadata-token: $tok" http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || true)"
  [ -n "$ip" ] || ip="$(curl -fsS -m 4 https://checkip.amazonaws.com 2>/dev/null | tr -d '[:space:]' || true)"
  printf '%s' "$ip"
}

site_url() {
  local d; d="$(envval DOMAIN)"
  if [ -n "$d" ]; then printf 'https://%s' "$d"; else printf 'http://%s' "$(public_ip)"; fi
}

check_env() {
  [ -f "$ENV_FILE" ] || die "$ENV_FILE does not exist.
  Create it:  cp $PROJ/deploy/aws/.env.aws.example $ENV_FILE && chmod 600 $ENV_FILE && nano $ENV_FILE"
  chmod 600 "$ENV_FILE" 2>/dev/null || true
  if grep -nE '^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*=.*CHANGE_ME' "$ENV_FILE" | sed -E 's/=.*/=.../' | sed 's/^/    still to fill in, line /' | grep .; then
    local ip; ip="$(public_ip)"
    die "$ENV_FILE still has CHANGE_ME values (listed above). Open it with: nano $ENV_FILE
  PUBLIC_SITE_URL for this server: http://${ip:-YOUR.ELASTIC.IP}   (or https://your-domain when DOMAIN is set)"
  fi
  local k
  for k in FINEDGE_API_KEY ADMIN_EMAIL ADMIN_PASSWORD SECRET_KEY CMS_JWT_SECRET POSTGRES_PASSWORD REDIS_PASSWORD PUBLIC_SITE_URL; do
    [ -n "$(envval "$k")" ] || die "$k is empty in $ENV_FILE"
  done
  local v
  v="$(envval SECRET_KEY)";      [ "${#v}" -ge 32 ] || die "SECRET_KEY must be at least 32 characters (openssl rand -base64 32)"
  v="$(envval CMS_JWT_SECRET)";  [ "${#v}" -ge 32 ] || die "CMS_JWT_SECRET must be at least 32 characters (openssl rand -base64 32)"
  v="$(envval ADMIN_PASSWORD)";  [ "${#v}" -ge 10 ] || die "ADMIN_PASSWORD must be at least 10 characters"
  envval POSTGRES_PASSWORD | grep -Eq '^[A-Za-z0-9_.~-]+$' || die "POSTGRES_PASSWORD may only contain letters, digits and _ . ~ - (use: openssl rand -hex 24)"
  envval REDIS_PASSWORD   | grep -Eq '^[A-Za-z0-9_.~-]+$' || die "REDIS_PASSWORD may only contain letters, digits and _ . ~ - (use: openssl rand -hex 24)"
  if grep -qE '^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*=[^'"'"'"]*[$]' "$ENV_FILE"; then
    die "a value in $ENV_FILE contains a dollar sign (\$), which Docker would read as a variable. Remove it or generate a new value."
  fi
  case "$(envval ADMIN_REQUIRE_MFA)" in 1|true|yes|on) ;; *) info "NOTE: ADMIN_REQUIRE_MFA is not 1: administrators can sign in without the authenticator app." ;; esac
}

git_sync() {
  command -v git >/dev/null || die "git is not installed: run bootstrap.sh first."
  local env_git=(GIT_TERMINAL_PROMPT=0)
  if [ -n "${GIT_TOKEN:-}" ]; then
    export GIT_TOKEN; ASKPASS="$(mktemp)"; chmod 700 "$ASKPASS"; local askpass="$ASKPASS"
    printf '#!/bin/sh\ncase "$1" in\n  Username*) echo x-access-token ;;\n  *) printf "%%s\\n" "$GIT_TOKEN" ;;\nesac\n' > "$askpass"
    env_git+=(GIT_ASKPASS="$askpass")
  fi
  if [ -d "$SRC/.git" ]; then
    say "Fetching $REPO_BRANCH from $REPO_URL"
    env "${env_git[@]}" git -C "$SRC" remote set-url origin "$REPO_URL"
    env "${env_git[@]}" git -C "$SRC" fetch --depth 1 origin "$REPO_BRANCH" || die "git fetch failed (network, wrong branch, or a private repository without GIT_TOKEN)."
    git -C "$SRC" reset --hard FETCH_HEAD >/dev/null
  else
    [ ! -e "$SRC" ] || [ -z "$(ls -A "$SRC" 2>/dev/null)" ] || die "$SRC exists but is not a git clone. Move it away and run again."
    say "Cloning $REPO_URL ($REPO_BRANCH) into $SRC"
    mkdir -p "$SRC"
    env "${env_git[@]}" git clone --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$SRC" || die "git clone failed (network, wrong branch, or a private repository without GIT_TOKEN)."
  fi
  [ -f "$PROJ/Dockerfile" ] || die "$PROJ/Dockerfile not found. Is REPO_SUBDIR ('$REPO_SUBDIR') the folder that holds the Dockerfile?"
  [ -f "$PROJ/deploy/aws/docker-compose.aws.yml" ] || die "deploy/aws/docker-compose.aws.yml is missing in $PROJ: is the branch up to date?"
  info "code is at commit $(git -C "$SRC" rev-parse --short HEAD): $(git -C "$SRC" log -1 --format=%s | cut -c1-70)"
}

wait_healthy() {  # wait_healthy -> 0 when /api/ping and then /api/health answer inside the app container
  local start now
  start="$(date +%s)"
  say "Waiting for the app (/api/ping), up to $((HEALTH_WAIT_S / 60)) minutes; the first start runs database migrations"
  until dc exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/ping', timeout=3)" >/dev/null 2>&1; do
    now="$(date +%s)"
    if [ $((now - start)) -ge "$HEALTH_WAIT_S" ]; then
      echo "The app did not answer in time. Last log lines:" >&2; dc logs --tail 40 app >&2 || true
      return 1
    fi
    sleep 5
  done
  info "/api/ping answers"
  say "Checking /api/health (database and cache)"
  until dc exec -T app python -c "import json,sys,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=8)); sys.exit(0 if d.get('ok') is True else 1)" >/dev/null 2>&1; do
    now="$(date +%s)"
    if [ $((now - start)) -ge $((HEALTH_WAIT_S + 180)) ]; then
      echo "/api/health does not report ok. Last log lines:" >&2; dc logs --tail 40 app >&2 || true
      return 1
    fi
    sleep 5
  done
  info "/api/health is ok"
  # the same through the front door (Caddy)
  local d code; d="$(envval DOMAIN)"
  if [ -n "$d" ]; then
    code="$(curl -ks -o /dev/null -w '%{http_code}' -m 10 --resolve "$d:443:127.0.0.1" "https://$d/api/ping" || true)"
    [ "$code" = 200 ] && info "https://$d answers" || info "https://$d does not answer yet (HTTP $code): the certificate can take a minute, and the DNS A record must point at this server. Check: bash $0 logs caddy"
  else
    code="$(curl -s -o /dev/null -w '%{http_code}' -m 10 http://127.0.0.1:${FRONT_HTTP_PORT:-80}/api/ping || true)"
    [ "$code" = 200 ] && info "the front door (Caddy, port 80) answers" || { echo "Caddy does not answer on port 80 (HTTP $code)" >&2; return 1; }
  fi
  return 0
}

image_id() { docker image inspect -f '{{.Id}}' "$1" 2>/dev/null || true; }
image_commit() { docker image inspect -f '{{index .Config.Labels "finlit.commit"}}' "$1" 2>/dev/null || true; }

cmd_deploy() {
  need_docker
  mkdir -p "$STATE"
  git_sync
  check_env
  local commit old_id new_id
  commit="$(git -C "$SRC" rev-parse --short HEAD)"; export GIT_COMMIT="$commit"
  old_id="$(image_id "$IMAGE:current")"
  [ -z "$old_id" ] || docker tag "$IMAGE:current" "$IMAGE:pending"   # a second name keeps the old build alive while the new one replaces "current"
  say "Building the image (first time 6-12 minutes on this small server; later builds reuse the cache)"
  dc build app
  new_id="$(image_id "$IMAGE:current")"
  if [ -n "$old_id" ]; then
    if [ "$old_id" != "$new_id" ]; then
      docker tag "$IMAGE:pending" "$IMAGE:previous"
      info "kept the previous build as $IMAGE:previous (commit $(image_commit "$IMAGE:previous"))"
    fi
    docker rmi "$IMAGE:pending" >/dev/null 2>&1 || true
  fi
  say "Starting everything"
  dc up -d --remove-orphans
  echo "$commit" > "$STATE/current_commit"
  # Caddyfile and backup.sh are single files mounted into containers; git replaces files with new ones, so a running container would keep
  # reading the old copy. When either changed since the last deploy, recreate those two containers (a second of downtime for the front door).
  local files_sha
  files_sha="$(cat "$PROJ/deploy/aws/Caddyfile" "$PROJ/deploy/aws/backup.sh" | sha256sum | cut -d' ' -f1)"
  if [ "$files_sha" != "$(cat "$STATE/mounted_files.sha" 2>/dev/null || true)" ]; then
    dc up -d --force-recreate --no-deps caddy backup
    echo "$files_sha" > "$STATE/mounted_files.sha"
  fi
  if ! wait_healthy; then
    echo >&2
    echo "The new version did not become healthy. To go back to the previous build:  bash $0 rollback" >&2
    exit 1
  fi
  docker image prune -f >/dev/null 2>&1 || true
  docker builder prune -f --filter until=168h >/dev/null 2>&1 || true
  say "Done: FinLit is running (commit $commit)"
  info "Open:        $(site_url)"
  info "Check it:    cd $PROJ && bash scripts/smoke.sh $(site_url)"
  info "Admin login: $(site_url)/login"
}

cmd_rollback() {
  need_docker
  [ -f "$ENV_FILE" ] || die "$ENV_FILE does not exist"
  [ -f "$PROJ/deploy/aws/docker-compose.aws.yml" ] || die "no checkout at $PROJ: nothing has been deployed here yet"
  [ -n "$(image_id "$IMAGE:previous")" ] || die "there is no previous build to go back to (only one deploy has been made)."
  say "Rolling back from commit $(image_commit "$IMAGE:current") to commit $(image_commit "$IMAGE:previous")"
  if [ -n "$(image_id "$IMAGE:current")" ]; then docker tag "$IMAGE:current" "$IMAGE:swap"; fi
  docker tag "$IMAGE:previous" "$IMAGE:current"
  if [ -n "$(image_id "$IMAGE:swap")" ]; then docker tag "$IMAGE:swap" "$IMAGE:previous"; docker rmi "$IMAGE:swap" >/dev/null 2>&1 || true; fi   # run rollback again to switch forward
  dc up -d --no-build --remove-orphans
  echo "$(image_commit "$IMAGE:current")" > "$STATE/current_commit" 2>/dev/null || true
  wait_healthy || die "the rolled-back app is not healthy either: see: bash $0 logs app"
  info "Rolled back. Database changes made by the newer version stay (migrations only go forward)."
  info "The next 'deploy.sh' pulls $REPO_BRANCH again and deploys the newest code, so fix the problem in the company repository first."
}

cmd_status() {
  need_docker
  [ -f "$PROJ/deploy/aws/docker-compose.aws.yml" ] || die "nothing deployed yet at $PROJ"
  say "Running code"
  info "image finlit-app:current   commit $(image_commit "$IMAGE:current")   built $(docker image inspect -f '{{.Created}}' "$IMAGE:current" 2>/dev/null | cut -c1-19)"
  info "previous (for rollback)    commit $(image_commit "$IMAGE:previous")"
  [ -d "$SRC/.git" ] && info "checkout on disk           commit $(git -C "$SRC" rev-parse --short HEAD) ($REPO_BRANCH)"
  say "Containers"
  dc ps -a || true
  say "Memory"
  free -h | sed 's/^/    /'
  local ids; mapfile -t ids < <(dc ps -q 2>/dev/null)
  [ "${#ids[@]}" -eq 0 ] || docker stats --no-stream --format '    {{.Name}}: {{.MemUsage}} ({{.MemPerc}}), cpu {{.CPUPerc}}' "${ids[@]}" 2>/dev/null || true
  say "Disk"
  df -h / | sed 's/^/    /'
  docker system df | sed 's/^/    /'
  if [ -f "$ENV_FILE" ]; then say "Address"; info "$(site_url)"; fi
}

cmd_logs() {
  need_docker
  [ -f "$PROJ/deploy/aws/docker-compose.aws.yml" ] || die "nothing deployed yet at $PROJ"
  if [ -n "${1:-}" ]; then
    case "$1" in app|db|redis|caddy|backup) ;; *) die "unknown service '$1' (app, db, redis, caddy, backup)";; esac
  fi
  dc logs --tail 200 -f ${1:+"$1"}
}

need_stack() {
  need_docker
  [ -f "$ENV_FILE" ] || die "$ENV_FILE does not exist"
  [ -f "$PROJ/deploy/aws/docker-compose.aws.yml" ] || die "nothing deployed yet at $PROJ"
}

cmd_restart() {
  need_stack
  dc restart ${1:+"$1"}
  info "restarted ${1:-everything}; the app needs about a minute: bash $0 status"
}

cmd_backup() { need_stack; dc exec -T backup /bin/sh /backup.sh once </dev/null; }

cmd_backups() { need_stack; dc exec -T backup sh -c 'ls -lh /backups' </dev/null; }

cmd_restore() {
  need_stack
  local f="${1:-}"
  [ -n "$f" ] || die "usage: deploy.sh restore FILE.dump   (names: bash $0 backups)"
  f="/backups/$(basename "$f")"
  dc exec -T backup test -f "$f" </dev/null || die "$f is not in the backups volume (see: bash $0 backups). A dump from elsewhere: dc cp it into /backups first (README)."
  echo "This ERASES the current database and loads $f. The site is stopped meanwhile. A safety backup is taken first."
  read -r -p "Type  restore  to go on: " ans
  [ "$ans" = restore ] || die "cancelled, nothing changed"
  dc stop app
  dc exec -T -e CONFIRM=yes backup /bin/sh /backup.sh restore "$f" </dev/null || { echo "restore failed: starting the app again with whatever is there" >&2; dc start app; exit 1; }
  dc start app
  wait_healthy || die "the app is not healthy after the restore: bash $0 logs app"
  info "Restore done."
}

main() {
  case "${1:-deploy}" in   # one deploy, rollback or restore at a time (a person and the automatic deploy must never overlap)
    deploy|rollback|restore) mkdir -p "$STATE"; exec 9>"$STATE/deploy.lock"; flock -n 9 || die "another deploy, rollback or restore is running right now: wait for it to finish" ;;
  esac
  case "${1:-deploy}" in
    deploy)   cmd_deploy ;;
    rollback) cmd_rollback ;;
    status)   cmd_status ;;
    logs)     shift; cmd_logs "$@" ;;
    restart)  shift; cmd_restart "$@" ;;
    backup)   cmd_backup ;;
    backups)  cmd_backups ;;
    restore)  shift; cmd_restore "$@" ;;
    compose)  shift; need_stack; dc "$@" ;;
    -h|--help|help) sed -n '2,19p' "$0" ;;
    *) die "unknown command '$1'. Use: deploy | rollback | status | logs [service] | restart [service] | backup | backups | restore FILE | compose ARGS" ;;
  esac
}
{ main "$@"; exit $?; }
