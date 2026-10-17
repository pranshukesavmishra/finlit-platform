#!/usr/bin/env bash
# Starts the local Postgres 16 cluster and Redis (idempotent) and makes sure the dev and test databases exist.
# Used on a fresh or restarted dev machine / cloud session before dev/run_stack.sh.
set -euo pipefail
pg_lsclusters | grep -q " online " || pg_ctlcluster 16 main start
for _ in $(seq 1 20); do pg_isready -q && break; sleep 0.5; done
redis-cli ping >/dev/null 2>&1 || redis-server --daemonize yes --save "" >/dev/null
su postgres -c "psql -tc \"select 1 from pg_roles where rolname='finlit'\"" | grep -q 1 || su postgres -c "psql -c \"create role finlit login superuser password 'finlit'\"" >/dev/null
for db in finlit_dev finlit_test; do
  su postgres -c "psql -tc \"select 1 from pg_database where datname='$db'\"" | grep -q 1 || su postgres -c "createdb -O finlit $db"
done
echo "postgres + redis up"
