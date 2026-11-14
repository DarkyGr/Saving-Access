#!/bin/sh
# Runs once, when the PostgreSQL volume is first initialised (task 32.6).
#
# Creates the least-privilege role the API connects with (Requirement 9.9):
# DML on tables, usage on sequences, nothing else. Default privileges make
# tables created later by migrations (run as the owner) usable too.
set -eu

psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v app_password="$APP_DB_PASSWORD" <<'SQL'
CREATE ROLE app_user LOGIN PASSWORD :'app_password'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
GRANT CONNECT ON DATABASE :"DBNAME" TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO app_user;
SQL
