#!/bin/sh
# PostgreSQL backups for the production stack (task 34.3).
#
# Runs in the "backup" service (postgres image, so pg_dump matches the
# server). Every BACKUP_INTERVAL_HOURS it writes a compressed custom-format
# dump to /backups, checks that pg_restore can read it, and deletes dumps
# older than BACKUP_RETENTION_DAYS.
#
#   backup.sh          loop forever (service command)
#   backup.sh once     one backup now, e.g.
#                      docker compose -f docker-compose.prod.yml exec backup sh /usr/local/bin/backup.sh once
#
# Dumps hold credentials encrypted with FERNET_KEY and bcrypt password
# hashes. Keep copies off the server, and keep FERNET_KEY stored separately:
# a dump is useless without it.
set -eu

: "${PGHOST:=db}"
: "${PGUSER:=savepass_owner}"
: "${PGDATABASE:=savepass}"
export PGHOST PGUSER PGDATABASE

DIR=/backups
INTERVAL=$(( ${BACKUP_INTERVAL_HOURS:-24} * 3600 ))
KEEP_DAYS=${BACKUP_RETENTION_DAYS:-14}
umask 077

run() {
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  final="$DIR/savepass-$ts.dump"
  tmp="$DIR/.savepass-$ts.partial"
  pg_dump --format=custom --file="$tmp"
  # Refuse to keep a dump that cannot be read back.
  pg_restore --list "$tmp" >/dev/null
  mv "$tmp" "$final"
  find "$DIR" -maxdepth 1 -name 'savepass-*.dump' -mtime +"$KEEP_DAYS" -delete
  echo "backup: $final ($(du -h "$final" | cut -f1))"
}

if [ "${1:-}" = "once" ]; then
  run
  exit 0
fi

until pg_isready -q; do sleep 2; done
while true; do
  run || { echo "backup: FAILED" >&2; rm -f "$DIR"/.savepass-*.partial; }
  sleep "$INTERVAL"
done
