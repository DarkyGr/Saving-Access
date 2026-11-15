<#
.SYNOPSIS
  Runs a command of the installed backend CLI (python -m app.cli) against the
  local installation's database, with its settings (task 36).
.DESCRIPTION
  Uses the installation's own Python and code (Y:\Apps\Save-Pass), so it runs
  exactly what is installed. The settings file is readable only by
  administrators: run it from an administrator terminal.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File ops\windows\with-production.ps1 create-admin --username admin --email you@example.com
  powershell -ExecutionPolicy Bypass -File ops\windows\with-production.ps1 verify-email --username alice
  powershell -ExecutionPolicy Bypass -File ops\windows\with-production.ps1 rotate-fernet-key --dry-run
#>
param(
    [Parameter(Mandatory = $true, Position = 0)][string]$Command,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest = @(),
    [string]$AppDir = 'Y:\Apps\Save-Pass'
)
. "$PSScriptRoot\common.ps1"

$python = Join-Path $AppDir 'python\python.exe'
if (-not (Test-Path $python)) { throw "Not installed: $python" }
& $python (Join-Path $AppDir 'ops\run.py') --env (Join-Path $AppDir '.env.production') --cwd (Join-Path $AppDir 'app') app.cli $Command @Rest
exit $LASTEXITCODE
