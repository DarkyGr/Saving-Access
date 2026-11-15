<#
.SYNOPSIS
  Checks what the local installation of Save-Pass needs, changing nothing
  (task 36). No administrator rights needed.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File ops\windows\00-check.ps1
#>
param(
    [string]$AppDir = 'Y:\Apps\Save-Pass',
    [string]$PgBin = 'C:\Program Files\PostgreSQL\18\bin',
    [string]$Mkcert = 'Y:\Code\Claude\tools\mkcert.exe'
)
. "$PSScriptRoot\common.ps1"

$rows = New-Object System.Collections.Generic.List[object]
function Check([string]$Item, [bool]$Ok, [string]$Hint) {
    $rows.Add([pscustomobject]@{ Item = $Item; Ok = $(if ($Ok) { 'yes' } else { 'NO' }); Hint = $(if ($Ok) { '' } else { $Hint }) })
}

$python = Get-Command python -ErrorAction SilentlyContinue
$pyOk = $false
if ($python) { $pyOk = (& python -c "import sys; print(sys.version_info >= (3, 11))") -eq 'True' }
Check 'Python 3.11+ (to build the runtime)' $pyOk 'Install Python 3.11 or newer; the release copies it into the install folder.'
Check 'Node.js / npm (to build the frontend)' ($null -ne (Get-Command npm -ErrorAction SilentlyContinue)) 'Install Node.js 20+.'
Check 'PostgreSQL 18 tools' (Test-Path (Join-Path $PgBin 'initdb.exe')) 'Install PostgreSQL 18 or pass -PgBin.'
$envFile = Join-Path $AppDir '.env.production'
Check 'Settings file' (Test-Path $envFile) 'Run: python scripts\release.py --to Y:\Apps\Save-Pass (it writes the template), then rename it.'
Check 'Database service savepass-postgres' ($null -ne (Get-Service $ServiceName -ErrorAction SilentlyContinue)) 'Run 01-postgres.ps1 as administrator.'
Check 'App installed' (Test-Path (Join-Path $AppDir 'app\app\main.py')) 'Run the release after the database exists.'
Check 'IIS installed' (Test-Path "$env:SystemRoot\System32\inetsrv\w3wp.exe") '03-iis.ps1 turns it on.'
Check 'IIS URL Rewrite' (Test-Path "$env:SystemRoot\System32\inetsrv\rewrite.dll") 'Install URL Rewrite 2.1 from https://www.iis.net/downloads/microsoft/url-rewrite'
Check 'IIS ARR (proxy)' (Test-Path "$env:ProgramFiles\IIS\Application Request Routing\requestRouter.dll") 'Install ARR 3.0 from https://www.iis.net/downloads/microsoft/application-request-routing'
Check 'mkcert' (Test-Path $Mkcert) 'Download mkcert to Y:\Code\Claude\tools and pass -Mkcert.'
Check 'Savings Tool authority (phone already trusts it)' (Test-Path (Join-Path $SavingsCaRoot 'rootCA.pem')) 'Optional: without it a new authority is made in Backup\certs and the phone must trust it too.'
$network = Get-NetConnectionProfile -ErrorAction SilentlyContinue | Select-Object -First 1
$profileName = if ($network) { $network.NetworkCategory } else { '' }
Check 'Home network is Private' ("$profileName" -eq 'Private') 'Settings > Network > your Wi-Fi > Private network.'

$port = 8443
if (Test-Path $envFile) { $port = [int](Read-EnvFile $envFile)['HTTPS_PORT'] }
$listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
$site = $null
try { Import-Module WebAdministration -ErrorAction Stop; $site = Get-Website -Name $SiteName -ErrorAction SilentlyContinue } catch { }
Check "HTTPS port $port free or ours" ((-not $listener) -or $site) "Port $port is used by another program: change HTTPS_PORT."

$rows | Format-Table -AutoSize
