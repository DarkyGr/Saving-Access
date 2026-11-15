<#
.SYNOPSIS
  Gives the superuser (postgres) of the Save-Pass cluster a new password when
  the one shown by 01-postgres.ps1 was lost (task 36). The app's roles and the
  data do not change.
.DESCRIPTION
  For a few seconds only postgres from this machine can connect without a
  password; the original access file always comes back, even on error.
.EXAMPLE
  Double click ops\windows\reset-postgres-password.cmd (it asks for administrator rights).
#>
param(
    [string]$AppDir = 'Y:\Apps\Save-Pass',
    [string]$PgBin = 'C:\Program Files\PostgreSQL\18\bin',
    [string]$PgData = 'Y:\Apps\Save-Pass\data\postgres',
    [string]$Service = 'savepass-postgres'
)
. "$PSScriptRoot\common.ps1"

try {
    Assert-Admin
    $port = (Get-DbParts (Read-EnvFile (Join-Path $AppDir '.env.production'))['DATABASE_URL']).Port
    $hba = Join-Path $PgData 'pg_hba.conf'
    $original = Get-Content -LiteralPath $hba -Raw
    $password = New-Secret 24
    try {
        Set-Content -LiteralPath $hba -Encoding ascii -NoNewline -Value ("host postgres postgres 127.0.0.1/32 trust`r`n" + $original)
        Restart-Service $Service
        Start-Sleep -Seconds 3
        & (Join-Path $PgBin 'psql.exe') --no-psqlrc -v ON_ERROR_STOP=1 -h 127.0.0.1 -p $port -U postgres -d postgres -c "ALTER ROLE postgres PASSWORD '$password'" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'The password could not be changed.' }
    } finally {
        Set-Content -LiteralPath $hba -Encoding ascii -NoNewline -Value $original
        Restart-Service $Service
    }
    Write-Done 'New password for postgres (shown only now; keep it in your password manager):'
    Write-Host "    $password"
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
}
Read-Host 'Enter para cerrar' | Out-Null
