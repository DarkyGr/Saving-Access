<#
.SYNOPSIS
  Creates the PostgreSQL 18 cluster of the local Save-Pass installation
  (task 36): data on Y:, its own Windows service, only on 127.0.0.1, the
  three roles and the database. No other PostgreSQL service is touched.
.DESCRIPTION
  Run as administrator after `python scripts\release.py` wrote .env.production
  (the role passwords come from its DATABASE_URL, DATABASE_URL_MIGRATOR and
  BACKUP_DATABASE_URL). Prints the superuser password once: keep it in your
  password manager.
    savepass_migrator  owner of the database; runs the migrations
    savepass_app       the API: SELECT/INSERT/UPDATE/DELETE only (Requirement 9.9)
    savepass_backup    reads everything for backups; may create the restore-test database
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File ops\windows\01-postgres.ps1
#>
param(
    [string]$AppDir = 'Y:\Apps\Save-Pass',
    [string]$PgBin = 'C:\Program Files\PostgreSQL\18\bin',
    [string]$PgData = 'Y:\Apps\Save-Pass\data\postgres',
    [string]$Service = 'savepass-postgres'
)
. "$PSScriptRoot\common.ps1"
Assert-Admin
Assert-NotOnC $PgData 'The database folder'

$settings = Read-EnvFile (Join-Path $AppDir '.env.production')
$app = Get-DbParts $settings['DATABASE_URL']
$migrator = Get-DbParts $settings['DATABASE_URL_MIGRATOR']
$backup = Get-DbParts $settings['BACKUP_DATABASE_URL']
foreach ($part in @($app, $migrator, $backup)) {
    if (-not $part.Password -or $part.Password -eq 'CHANGE_ME') { throw 'Set the role passwords in .env.production first.' }
}
$port = $app.Port
$database = $app.Database

if (Get-Service $Service -ErrorAction SilentlyContinue) {
    Write-Note "The service $Service already exists: nothing to create. To start over, remove it and its folder by hand."
    exit 0
}
if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $port is already in use: change it in the three database URLs of .env.production."
}
if ((Test-Path $PgData) -and (Get-ChildItem -LiteralPath $PgData -Force | Select-Object -First 1)) {
    throw "$PgData is not empty."
}

Write-Step "Creating the cluster in $PgData"
New-Item -ItemType Directory -Force -Path $PgData | Out-Null
$superPassword = New-Secret 24
$pwFile = Join-Path $AppDir 'initdb-password.tmp'
Set-Content -LiteralPath $pwFile -Value $superPassword -NoNewline -Encoding ascii
try {
    & (Join-Path $PgBin 'initdb.exe') -D $PgData -U postgres -A scram-sha-256 "--pwfile=$pwFile" -E UTF8 --locale-provider=builtin --builtin-locale=C.UTF-8
    if ($LASTEXITCODE -ne 0) { throw 'initdb failed.' }
} finally { Remove-Item -LiteralPath $pwFile -Force -ErrorAction SilentlyContinue }

# Only this machine, only with a password.
Add-Content -LiteralPath (Join-Path $PgData 'postgresql.conf') -Value @"

# Save-Pass
listen_addresses = '127.0.0.1'
port = $port
"@
Set-Content -LiteralPath (Join-Path $PgData 'pg_hba.conf') -Encoding ascii -Value @'
# TYPE  DATABASE  USER  ADDRESS        METHOD
host    all       all   127.0.0.1/32   scram-sha-256
host    all       all   ::1/128        scram-sha-256
'@

Write-Step "Registering the service $Service (Network Service account)"
& icacls $PgData /grant "${ServiceAccount}:(OI)(CI)M" | Out-Null
& (Join-Path $PgBin 'pg_ctl.exe') register -N $Service -D $PgData -S auto -U $ServiceAccount
if ($LASTEXITCODE -ne 0) { throw 'pg_ctl register failed.' }
Start-Service $Service

Write-Step 'Creating the roles and the database'
$esc = { param($s) $s.Replace("'", "''") }
$sql = @"
CREATE ROLE $($migrator.User) LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '$(& $esc $migrator.Password)';
CREATE ROLE $($app.User) LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD '$(& $esc $app.Password)';
CREATE ROLE $($backup.User) LOGIN CREATEDB NOSUPERUSER NOCREATEROLE PASSWORD '$(& $esc $backup.Password)';
GRANT pg_read_all_data TO $($backup.User);
CREATE DATABASE $database OWNER $($migrator.User);
REVOKE CONNECT ON DATABASE $database FROM PUBLIC;
GRANT CONNECT ON DATABASE $database TO $($migrator.User), $($app.User), $($backup.User);
\connect $database
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO $($migrator.User);
GRANT USAGE ON SCHEMA public TO $($app.User), $($backup.User);
ALTER DEFAULT PRIVILEGES FOR ROLE $($migrator.User) IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO $($app.User);
ALTER DEFAULT PRIVILEGES FOR ROLE $($migrator.User) IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO $($app.User);
ALTER DEFAULT PRIVILEGES FOR ROLE $($migrator.User) IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO $($app.User);
"@
$env:PGPASSWORD = $superPassword
try {
    $sql | & (Join-Path $PgBin 'psql.exe') --no-psqlrc -v ON_ERROR_STOP=1 -h 127.0.0.1 -p $port -U postgres -d postgres
    if ($LASTEXITCODE -ne 0) { throw 'Creating the roles failed.' }
} finally { Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue }

Write-Done "Cluster ready on 127.0.0.1:$port (service $Service, automatic start)."
Write-Host ''
Write-Note "Superuser 'postgres' password (shown only now; keep it in your password manager):"
Write-Host "    $superPassword"
Write-Host ''
Write-Host 'Next: python scripts\release.py --to Y:\Apps\Save-Pass   (applies the migrations to this database)'
