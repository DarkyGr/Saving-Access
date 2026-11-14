#!/usr/bin/env bash
# Smoke test of the production stack (docker-compose.prod.yml), task 32.7.
# Builds and starts everything with throwaway secrets on https://localhost,
# checks TLS + security headers, a full API round trip through Caddy, and that
# the API's database role cannot change the schema. Tears everything down.
#
#   ./scripts/smoke-prod.sh
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=$(mktemp)
COMPOSE=(docker compose -f docker-compose.prod.yml --env-file "$ENV_FILE" -p savepass-smoke)
gen() { python3 -c "import secrets; print(secrets.token_urlsafe($1))"; }
{
  echo "SITE_ADDRESS=localhost"
  echo "DB_OWNER_PASSWORD=$(gen 24)"
  echo "APP_DB_PASSWORD=$(gen 24)"
  echo "JWT_SECRET=$(gen 48)"
  echo "FERNET_KEY=$(python3 -c 'import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
} > "$ENV_FILE"

cleanup() { "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true; rm -f "$ENV_FILE"; }
trap cleanup EXIT

"${COMPOSE[@]}" up -d --build

BASE=https://localhost
CURL=(curl -fsS -k --retry 5 --retry-connrefused --retry-delay 2)
JAR=$(mktemp)

echo "• waiting for the stack (migrations, API health, Caddy)"
for _ in $(seq 1 90); do
  if curl -fsk "$BASE/api/health" 2>/dev/null | grep -q '"ok"'; then break; fi
  sleep 2
done
curl -fsk "$BASE/api/health" | grep -q '"ok"' || { "${COMPOSE[@]}" ps; "${COMPOSE[@]}" logs --tail 50; exit 1; }
[ "$(docker inspect -f '{{.State.ExitCode}}' "$("${COMPOSE[@]}" ps -aq migrate)")" = "0" ]

echo "• security headers"
HEADERS=$("${CURL[@]}" -D - -o /dev/null "$BASE/")
for h in "strict-transport-security: max-age=31536000" "x-frame-options: DENY" "content-security-policy:" "x-content-type-options: nosniff"; do
  grep -qi "^$h" <<<"$HEADERS" || { echo "missing header: $h"; exit 1; }
done

echo "• HTTP redirects to HTTPS"
curl -sS -o /dev/null -w '%{http_code}' http://localhost/ | grep -qE '^30[18]$'

echo "• SPA served with history fallback"
"${CURL[@]}" "$BASE/credentials" | grep -qi '<div id="root">'

PW='Str0ngPassw0rd!'
echo "• register → login → save → reveal → refresh → logout"
"${CURL[@]}" -H 'Content-Type: application/json' \
  -d "{\"username\":\"smoke\",\"email\":\"smoke@example.com\",\"password\":\"$PW\",\"password_confirmation\":\"$PW\"}" \
  "$BASE/api/auth/register" >/dev/null
TOKEN=$("${CURL[@]}" -c "$JAR" -H 'Content-Type: application/json' \
  -d "{\"username\":\"smoke\",\"password\":\"$PW\"}" "$BASE/api/auth/login" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
grep -q sp_refresh "$JAR"
AUTH=(-H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json')
CID=$("${CURL[@]}" "${AUTH[@]}" \
  -d "{\"website_name\":\"GitHub\",\"email_or_username\":\"smoke@example.com\",\"password\":\"gh-secret\",\"account_password\":\"$PW\"}" \
  "$BASE/api/credentials" | python3 -c 'import json,sys; print(json.load(sys.stdin)["credential_id"])')
"${CURL[@]}" "${AUTH[@]}" -d "{\"account_password\":\"$PW\"}" "$BASE/api/credentials/$CID/reveal" | grep -q gh-secret
"${CURL[@]}" -b "$JAR" -c "$JAR" -X POST "$BASE/api/auth/refresh" | grep -q access_token
"${CURL[@]}" -b "$JAR" -X POST "$BASE/api/auth/logout" -o /dev/null

echo "• audit rows written"
"${COMPOSE[@]}" exec -T db psql -U savepass_owner -d savepass -tAc \
  "select string_agg(operation, ',' order by operation) from audit_log" | grep -qx 'INSERT,SELECT'

echo "• app_user cannot change the schema"
for stmt in "DROP TABLE audit_log" "CREATE TABLE evil(id int)" "TRUNCATE users"; do
  if "${COMPOSE[@]}" exec -T db sh -c "PGPASSWORD=\"\$APP_DB_PASSWORD\" psql -h localhost -U app_user -d savepass -v ON_ERROR_STOP=1 -c '$stmt'" >/dev/null 2>&1; then
    echo "app_user was allowed to: $stmt"; exit 1
  fi
done

echo "Production smoke test passed."
