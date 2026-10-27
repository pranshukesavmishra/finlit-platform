#!/bin/sh
# Database backups, run inside the "backup" container (the database image, so pg_dump matches the server). POSIX sh.
#   backup.sh loop            every night at 20:30 UTC (02:00 IST)   <- what the container does
#   backup.sh once            one backup now
#   backup.sh restore FILE    replace the live database with a dump (needs CONFIRM=yes; stop the app first, see the README)
# Files: /backups/finlit-YYYY-MM-DD_HHMMSS.dump (pg_dump custom format, already compressed), newest KEEP_DAYS days kept.
# The connection comes from PGHOST / PGUSER / PGDATABASE / PGPASSWORD in the container's environment (never on a command line).
set -eu
DIR=/backups
KEEP_DAYS="${KEEP_DAYS:-7}"
log() { echo "$(date -u '+%F %T') UTC backup: $*"; }

do_backup() {
  stamp="$(date -u '+%Y-%m-%d_%H%M%S')"
  tmp="$DIR/.tmp-$stamp.dump"
  out="$DIR/finlit-$stamp.dump"
  if pg_dump --format=custom --compress=6 --no-owner --no-privileges --file="$tmp" && pg_restore --list "$tmp" >/dev/null 2>&1; then
    mv "$tmp" "$out"
    log "saved $out ($(du -h "$out" | cut -f1))"
    find "$DIR" -name 'finlit-*.dump' -type f -mtime +"$((KEEP_DAYS - 1))" -exec rm -f {} + 2>/dev/null || true
    return 0
  fi
  rm -f "$tmp"
  log "FAILED (the database may be down); the older backups are untouched"
  return 1
}

do_restore() {
  file="${1:-}"
  [ -n "$file" ] || { echo "usage: backup.sh restore /backups/FILE.dump" >&2; exit 2; }
  [ -f "$file" ] || { echo "no such file: $file" >&2; exit 2; }
  [ "${CONFIRM:-}" = yes ] || { echo "This ERASES the current database and loads $file. Run again with CONFIRM=yes to go on." >&2; exit 2; }
  pg_restore --list "$file" >/dev/null || { echo "$file is not a readable pg_dump file" >&2; exit 2; }
  log "taking a safety copy of the current database first"
  do_backup || { echo "could not take the safety copy: stopping, nothing changed" >&2; exit 1; }
  # maintenance database "postgres": the target cannot be dropped while connected to it
  PGDATABASE=postgres psql -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS finlit WITH (FORCE)" -c "CREATE DATABASE finlit"
  has_ts=0
  pg_restore --list "$file" | grep -q 'EXTENSION - timescaledb' && has_ts=1
  if [ "$has_ts" = 1 ]; then
    psql -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS timescaledb" -c "SELECT timescaledb_pre_restore()"
  fi
  # A dump from plain Postgres (for example Neon) has no TimescaleDB parts: the app converts price_daily by itself at its next start.
  # Warnings about objects that already exist are normal; the result is checked by looking at the site.
  pg_restore --no-owner --no-privileges --dbname=finlit "$file" || log "pg_restore reported errors (see above); check the site before deleting anything"
  if [ "$has_ts" = 1 ]; then
    psql -v ON_ERROR_STOP=1 -c "SELECT timescaledb_post_restore()"
  fi
  log "restore finished; start the app again"
}

case "${1:-}" in
  loop)
    mkdir -p "$DIR"
    while true; do
      now="$(date -u +%s)"
      wait=$(( (20 * 3600 + 30 * 60 - now % 86400 + 86400) % 86400 ))
      log "next backup in $((wait / 60)) minutes"
      sleep "$wait"
      do_backup || true
      sleep 120   # never twice in the same minute
    done
    ;;
  once) mkdir -p "$DIR"; do_backup ;;
  restore) shift; do_restore "$@" ;;
  *) echo "usage: backup.sh loop | once | restore FILE" >&2; exit 2 ;;
esac
