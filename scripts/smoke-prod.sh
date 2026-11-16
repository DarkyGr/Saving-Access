#!/usr/bin/env bash
# Smoke test of the production stack (docker-compose.prod.yml), task 32.7.
# Builds and starts everything with throwaway secrets on https://localhost,
# checks TLS + security headers, a full API round trip through Caddy, the
# shared (Redis) rate limit, backup + restore, and that the API's database
# role cannot change the schema. Tears everything down.
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
  echo "EMAIL_VERIFICATION_ENABLED=true"   # console email backend
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
echo "• register → login → set up 2FA → save → reveal → refresh"
"${CURL[@]}" -H 'Content-Type: application/json' \
  -d "{\"username\":\"smoke\",\"email\":\"smoke@example.com\",\"password\":\"$PW\",\"password_confirmation\":\"$PW\"}" \
  "$BASE/api/auth/register" >/dev/null
# Task 37.5: production requires two-factor; the first sign-in sets it up.
MFA=$("${CURL[@]}" -H 'Content-Type: application/json' \
  -d "{\"username\":\"smoke\",\"password\":\"$PW\"}" "$BASE/api/auth/login" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["mfa"]=="setup" and not d["access_token"]; print(d["mfa_token"])')
SECRET=$("${CURL[@]}" -H 'Content-Type: application/json' -d "{\"mfa_token\":\"$MFA\"}" "$BASE/api/auth/2fa/setup" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["secret"])')
CODE=$(python3 - "$SECRET" <<'PY'
import base64, hashlib, hmac, struct, sys, time
key = base64.b32decode(sys.argv[1] + "=" * (-len(sys.argv[1]) % 8))
digest = hmac.new(key, struct.pack(">Q", int(time.time() // 30)), hashlib.sha1).digest()
offset = digest[-1] & 15
print(str((struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1000000).zfill(6))
PY
)
TOKEN=$("${CURL[@]}" -c "$JAR" -H 'Content-Type: application/json' \
  -d "{\"mfa_token\":\"$MFA\",\"code\":\"$CODE\"}" "$BASE/api/auth/2fa/confirm" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); assert len(d["recovery_codes"])==10; print(d["access_token"])')
grep -q sp_refresh "$JAR"
AUTH=(-H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json')
CID=$("${CURL[@]}" "${AUTH[@]}" \
  -d "{\"website_name\":\"GitHub\",\"email_or_username\":\"smoke@example.com\",\"password\":\"gh-secret\",\"account_password\":\"$PW\"}" \
  "$BASE/api/credentials" | python3 -c 'import json,sys; print(json.load(sys.stdin)["credential_id"])')
"${CURL[@]}" "${AUTH[@]}" -d "{\"account_password\":\"$PW\"}" "$BASE/api/credentials/$CID/reveal" | grep -q gh-secret
"${CURL[@]}" -b "$JAR" -c "$JAR" -X POST "$BASE/api/auth/refresh" | grep -q access_token

echo "• login rate limit is shared by the API workers (Redis)"
codes=""
for _ in $(seq 1 12); do
  codes+=$(curl -sk -o /dev/null -w '%{http_code} ' -H 'Content-Type: application/json' \
    -d '{"username":"nobody","password":"wrong"}' "$BASE/api/auth/login")
done
echo "  $codes"
# 10/minute per IP: with per-process counters and 2 workers, 12 attempts
# could all pass; with Redis the 11th and 12th must be refused.
[ "$(tr ' ' '\n' <<<"$codes" | grep -c '^429$')" -ge 2 ]
"${COMPOSE[@]}" exec -T redis redis-cli --scan --pattern 'LIMITS:*' | grep -q .

echo "• audit rows written"
# Task 37.4: every row names its action (failed logins write none).
"${COMPOSE[@]}" exec -T db psql -U savepass_owner -d savepass -tAc \
  "select string_agg(distinct action, ',' order by action) from audit_log" \
  | grep -qx 'account.2fa_setup,account.login,account.register,credential.create,credential.reveal'

echo "• backup, data loss, restore"
"${COMPOSE[@]}" exec -T backup sh /usr/local/bin/backup.sh once
DUMP=$("${COMPOSE[@]}" exec -T backup sh -c 'ls -t /backups/savepass-*.dump | head -1' | tr -d '\r')
DUMP=$(basename "$DUMP")
psql_owner() { "${COMPOSE[@]}" exec -T db psql -U savepass_owner -d savepass -tAc "$1"; }
psql_owner "DELETE FROM credentials" >/dev/null
[ "$(psql_owner 'select count(*) from credentials')" = "0" ]
RESTORE_CONFIRM=yes COMPOSE_CMD="${COMPOSE[*]}" ./scripts/restore-backup.sh "$DUMP"
[ "$(psql_owner 'select count(*) from credentials')" = "1" ]
for _ in $(seq 1 60); do
  if curl -fsk "$BASE/api/health" 2>/dev/null | grep -q '"ok"'; then break; fi
  sleep 2
done
# The restored rows are readable by the API as app_user and still decrypt.
"${CURL[@]}" "${AUTH[@]}" -d "{\"account_password\":\"$PW\"}" "$BASE/api/credentials/$CID/reveal" | grep -q gh-secret

echo "• logout ends the session and its access token at once"
"${CURL[@]}" -b "$JAR" -X POST "$BASE/api/auth/logout" -o /dev/null
[ "$(curl -sk -o /dev/null -w '%{http_code}' "${AUTH[@]}" "$BASE/api/credentials")" = "401" ]

echo "• reminder scheduler runs as app_user"
psql_owner "UPDATE users SET deactivation_deadline = current_date + 1 WHERE username = 'smoke'" >/dev/null
"${COMPOSE[@]}" exec -T scheduler python -m app.cli send-verification-reminders | grep -q "Reminded 1 user(s): smoke"
"${COMPOSE[@]}" exec -T scheduler python -m app.cli send-verification-reminders | grep -q "Reminded 0 user(s)"

echo "• app_user cannot change the schema"
for stmt in "DROP TABLE audit_log" "CREATE TABLE evil(id int)" "TRUNCATE users"; do
  if "${COMPOSE[@]}" exec -T db sh -c "PGPASSWORD=\"\$APP_DB_PASSWORD\" psql -h localhost -U app_user -d savepass -v ON_ERROR_STOP=1 -c '$stmt'" >/dev/null 2>&1; then
    echo "app_user was allowed to: $stmt"; exit 1
  fi
done

echo "Production smoke test passed."
