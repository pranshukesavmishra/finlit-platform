#!/usr/bin/env bash
# Weekly backup of both databases into ONE encrypted file you keep somewhere private. Run it on your own computer.
#   NEON_URL='postgresql://...'   (Neon "direct" connection string; NOT the -pooler one)
#   MONGO_URL='mongodb+srv://...' (MongoDB Atlas connection string)  [optional: skipped if empty]
#   BACKUP_PASSPHRASE='a long phrase you will remember'
#   ./scripts/backup.sh [output-folder]
# Needs: pg_dump (PostgreSQL client), mongodump (MongoDB Database Tools, optional), and openssl.
# Restore: see docs/deploy-free.md ("Restoring a backup"). Never commit the output file: it contains member data.
set -euo pipefail
: "${NEON_URL:?set NEON_URL to the Neon direct connection string}"
: "${BACKUP_PASSPHRASE:?set BACKUP_PASSPHRASE (used to encrypt the backup)}"
OUT="${1:-$HOME/finlit-backups}"; STAMP="$(date +%Y-%m-%d)"; WORK="$(mktemp -d)"; mkdir -p "$OUT"
trap 'rm -rf "$WORK" "$WORK.tgz"' EXIT
echo "1/3 Postgres (Neon)..."
pg_dump --format=custom --no-owner --no-privileges --file="$WORK/postgres.dump" "$NEON_URL"
if [ -n "${MONGO_URL:-}" ]; then
  echo "2/3 MongoDB (Atlas)..."
  if command -v mongodump >/dev/null; then mongodump --uri="$MONGO_URL" --db="${DB_NAME:-finlit}" --archive="$WORK/mongo.archive" --gzip
  else echo "   mongodump is not installed: skipping MongoDB (install 'MongoDB Database Tools' or use Atlas's own snapshots)"; fi
else echo "2/3 MongoDB: MONGO_URL not set, skipped"; fi
echo "3/3 Packing and encrypting..."
tar -C "$WORK" -czf "$WORK.tgz" .   # the archive goes next to the folder, not inside it
openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:BACKUP_PASSPHRASE -in "$WORK.tgz" -out "$OUT/finlit-$STAMP.tgz.enc"
ls -lh "$OUT/finlit-$STAMP.tgz.enc"
echo "Done. Keep this file somewhere private (not in the repository) and delete copies older than about 8 weeks."
