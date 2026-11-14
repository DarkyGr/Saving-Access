#!/usr/bin/env bash
# Restore a PostgreSQL backup into the production stack (task 34.3).
#
#   ./scripts/restore-backup.sh savepass-20261114T030000Z.dump   # a dump in the backups volume
#   ./scripts/restore-backup.sh ./offsite/savepass-….dump        # a local file (copied in first)
#   ./scripts/restore-backup.sh --list                           # list available dumps
#
# The API is stopped while the database is replaced in one transaction, then
# started again. FERNET_KEY must be the key the dump was taken with.
#
# Env: COMPOSE_CMD (default: docker compose -f docker-compose.prod.yml --env-file .env.prod)
#      RESTORE_CONFIRM=yes  skip the confirmation prompt
set -euo pipefail
cd "$(dirname "$0")/.."

read -r -a COMPOSE <<<"${COMPOSE_CMD:-docker compose -f docker-compose.prod.yml --env-file .env.prod}"
ARG=${1:?usage: restore-backup.sh <dump name or file> | --list}

if [ "$ARG" = "--list" ]; then
  "${COMPOSE[@]}" exec -T backup sh -c 'ls -lh /backups/savepass-*.dump 2>/dev/null || echo "no backups yet"'
  exit 0
fi

if [ -f "$ARG" ]; then
  NAME=$(basename "$ARG")
  "${COMPOSE[@]}" cp "$ARG" "backup:/backups/$NAME"
else
  NAME=$ARG
fi
case "$NAME" in */* | "") echo "invalid dump name: $NAME" >&2; exit 1 ;; esac
"${COMPOSE[@]}" exec -T backup test -f "/backups/$NAME" || { echo "not found: /backups/$NAME" >&2; exit 1; }

if [ "${RESTORE_CONFIRM:-}" != "yes" ]; then
  read -r -p "This REPLACES the current database with $NAME. Type 'restore' to continue: " answer
  [ "$answer" = "restore" ] || { echo "aborted"; exit 1; }
fi

echo "• stopping the API"
"${COMPOSE[@]}" stop backend
restart_api() { "${COMPOSE[@]}" start backend >/dev/null; }
trap restart_api EXIT

echo "• restoring $NAME"
"${COMPOSE[@]}" exec -T backup pg_restore \
  -h db -U savepass_owner -d savepass \
  --clean --if-exists --single-transaction --exit-on-error "/backups/$NAME"

echo "• starting the API"
trap - EXIT
restart_api
echo "Restore finished."
