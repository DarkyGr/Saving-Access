# Shared helpers of the local start/stop scripts (development only, task 36).
# Same model as Savings Tool. Compatible with Windows PowerShell 5.1.

$script:Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script:StateFile = Join-Path $Root 'Backup\tmp\local-dev.json'
# Output of the docker commands of the last run.
$script:LogFile = Join-Path $Root 'Backup\logs\local-dev.log'
# What the scripts themselves did.
$script:ControlLog = Join-Path $Root 'Backup\logs\local-control.log'
$script:WebPort = 5173
$script:ApiPort = 8000

function Write-Step([string]$Text) { Write-Host "[Save-Pass] $Text" }

function Add-Log([string]$Text) {
  $dir = Split-Path $ControlLog
  if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
  Add-Content -Path $ControlLog -Value "$(Get-Date -Format s) $Text" -ErrorAction SilentlyContinue
}

function Read-State {
  if (-not (Test-Path $StateFile)) { return $null }
  try { return Get-Content $StateFile -Raw | ConvertFrom-Json } catch { return $null }
}

function Write-State($State) {
  $dir = Split-Path $StateFile
  if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
  $State | ConvertTo-Json | Set-Content -Path $StateFile -Encoding ASCII
}

function Get-ProcessInfo([int]$Id) {
  Get-CimInstance Win32_Process -Filter "ProcessId=$Id" -ErrorAction SilentlyContinue
}

function Stop-Tree([int]$Id) {
  & cmd.exe /c "taskkill /PID $Id /T /F >nul 2>&1"
}

function Test-Port([int]$Port) {
  $client = New-Object System.Net.Sockets.TcpClient
  try {
    $client.Connect('127.0.0.1', $Port)
    return $true
  } catch {
    return $false
  } finally {
    $client.Close()
  }
}

function Test-Docker {
  & cmd.exe /c "docker info >nul 2>&1"
  return $LASTEXITCODE -eq 0
}

function Find-DockerDesktop {
  $candidates = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe'),
    (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe')
  )
  return $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}

# Returns $true when this call had to start Docker.
function Start-DockerIfNeeded {
  if (Test-Docker) { return $false }
  Write-Step 'Docker no esta encendido: iniciandolo...'
  # The CLI starts the engine without opening the Docker Desktop window.
  & cmd.exe /c "docker desktop start --detach >nul 2>&1"
  if ($LASTEXITCODE -ne 0) {
    $exe = Find-DockerDesktop
    if (-not $exe) { throw 'Docker Desktop was not found.' }
    Start-Process -FilePath $exe -WindowStyle Hidden
  }
  for ($i = 0; $i -lt 90; $i++) {
    if (Test-Docker) { return $true }
    Start-Sleep -Seconds 2
  }
  throw 'Docker did not start in 3 minutes.'
}

function Invoke-Logged([string]$Command) {
  Add-Content -Path $LogFile -Value "> $Command"
  Push-Location $Root
  try {
    & cmd.exe /c "$Command >> `"$LogFile`" 2>&1"
    if ($LASTEXITCODE -ne 0) { throw "Failed: $Command (see $LogFile)" }
  } finally {
    Pop-Location
  }
}

# Removes the containers and their network; the data lives in a volume and stays.
function Stop-Containers {
  if (Test-Docker) {
    Write-Step 'Bajando los contenedores (tus datos se conservan)...'
    Invoke-Logged 'docker compose down'
  }
}

function Stop-DockerDesktop {
  Write-Step 'Cerrando Docker, que abrio este script...'
  & cmd.exe /c "docker desktop stop >nul 2>&1"
  if ($LASTEXITCODE -ne 0) {
    Get-Process 'Docker Desktop', 'com.docker.backend' -ErrorAction SilentlyContinue |
      Stop-Process -Force -ErrorAction SilentlyContinue
  }
}

# A port of ours must be free before starting; another program's is never touched.
function Assert-PortFree([int]$Port) {
  if (-not (Test-Port $Port)) { return }
  $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  $owner = if ($connection) { Get-ProcessInfo $connection.OwningProcess } else { $null }
  $name = if ($owner) { "$($owner.Name), PID $($owner.ProcessId)" } else { 'unknown' }
  if ($owner -and $owner.Name -match '^(com\.docker|wslrelay|vpnkit|docker)') { return }
  throw "Port $Port is in use by another program ($name). Nothing was stopped."
}
