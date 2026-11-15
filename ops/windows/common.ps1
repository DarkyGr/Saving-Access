# Shared helpers of the Save-Pass local installation scripts (task 36).
# Same model as Savings Tool phase 8. Dot-source it: . "$PSScriptRoot\common.ps1"
# Works in Windows PowerShell 5.1 and PowerShell 7.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoDir = (Resolve-Path "$PSScriptRoot\..\..").Path
$DefaultAppDir = 'Y:\Apps\Save-Pass'
$TaskFolder = '\Save-Pass\'
$ServiceAccount = 'NT AUTHORITY\NETWORK SERVICE'
$ServiceName = 'savepass-postgres'
$SiteName = 'Save-Pass'
$DefaultPgBin = 'C:\Program Files\PostgreSQL\18\bin'
$DefaultMkcert = 'Y:\Code\Claude\tools\mkcert.exe'
# mkcert authority shared with Savings Tool: the phone already trusts it.
$SavingsCaRoot = 'Y:\Code\Git\Repos\Savings-Tool\Backup\certs'

function Read-EnvFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { throw "Settings file not found: $Path" }
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$') { $values[$Matches[1]] = $Matches[2].Trim('"') }
    }
    return $values
}

# User, password, port and database of a postgresql:// URI.
function Get-DbParts([string]$Uri) {
    $u = [Uri]$Uri
    $user, $pass = $u.UserInfo.Split(':', 2)
    return @{
        User     = [Uri]::UnescapeDataString($user)
        Password = [Uri]::UnescapeDataString($pass)
        Port     = $u.Port
        Database = $u.AbsolutePath.Trim('/')
    }
}

function Assert-Admin {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run this script as administrator.'
    }
}

function Assert-NotOnC([string]$Path, [string]$What) {
    if ($Path -match '^[Cc]:') { throw "$What must not be on C: ($Path)." }
}

function New-Secret([int]$Bytes = 24) {
    $buffer = New-Object byte[] $Bytes
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($buffer) } finally { $rng.Dispose() }
    return ([Convert]::ToBase64String($buffer)).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Get-CaRoot([string]$CaRoot) {
    if ($CaRoot) { return $CaRoot }
    if (Test-Path -LiteralPath (Join-Path $SavingsCaRoot 'rootCA.pem')) { return $SavingsCaRoot }
    return (Join-Path $RepoDir 'Backup\certs')
}

function Write-Step([string]$Text) { Write-Host "==> $Text" -ForegroundColor Cyan }
function Write-Done([string]$Text) { Write-Host "OK  $Text" -ForegroundColor Green }
function Write-Note([string]$Text) { Write-Host "!!  $Text" -ForegroundColor Yellow }
