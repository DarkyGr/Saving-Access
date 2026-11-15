# Starts (or restarts) everything for local development, in the background:
# Docker if needed and the containers (PostgreSQL, API with the migrations,
# Vite). It stops by itself after -AutoStopMinutes. A second run takes down
# the first one and starts over. Same model as Savings Tool (task 36).
param(
  [double]$AutoStopMinutes = 30
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'local-common.ps1')

try {
  $previous = Read-State
  Add-Log 'restart requested'
  if ($previous -and $previous.watchdogPid -and (Get-ProcessInfo $previous.watchdogPid)) {
    Stop-Tree $previous.watchdogPid
  }
  if (-not (Test-Path (Join-Path $Root '.env'))) {
    throw 'Missing .env: copy .env.example to .env and fill in JWT_SECRET and FERNET_KEY (see README).'
  }
  # One log per run: they never grow from one day to the next.
  Set-Content -Path $LogFile -Value "$(Get-Date -Format s) start"
  Set-Content -Path $ControlLog -Value "$(Get-Date -Format s) start"

  $startedDocker = [bool]($previous -and $previous.startedDocker)
  if (Start-DockerIfNeeded) { $startedDocker = $true }
  Write-Step 'Reiniciando los contenedores (la API aplica las migraciones al arrancar)...'
  Invoke-Logged 'docker compose down'
  foreach ($port in $ApiPort, $WebPort) { Assert-PortFree $port }
  Invoke-Logged 'docker compose up -d --build --wait --wait-timeout 180'

  $runId = [guid]::NewGuid().ToString()
  $stopAt = (Get-Date).AddMinutes($AutoStopMinutes)
  $state = [ordered]@{
    runId = $runId
    watchdogPid = 0
    startedDocker = $startedDocker
    stopAt = $stopAt.ToString('o')
  }
  Write-State $state

  $ready = $false
  for ($i = 0; $i -lt 90; $i++) {
    if ((Test-Port $WebPort) -and (Test-Port $ApiPort)) { $ready = $true; break }
    Start-Sleep -Seconds 1
  }
  if (-not $ready) { throw "The app did not start (see $LogFile and: docker compose logs)." }

  $stopScript = Join-Path $PSScriptRoot 'stop-local.ps1'
  $watchdog = Start-Process -FilePath 'powershell.exe' -ArgumentList @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
    '-File', "`"$stopScript`"", '-RunId', $runId
  ) -WindowStyle Hidden -PassThru
  $state.watchdogPid = $watchdog.Id
  Write-State $state

  Write-Step "Listo: http://localhost:$WebPort  (API: http://localhost:$ApiPort/docs)"
  Write-Step "Se apaga solo a las $($stopAt.ToString('HH:mm')). Para apagarlo antes: stop-local.cmd"
  Start-Sleep -Seconds 6
} catch {
  Write-Host "[Save-Pass] ERROR: $($_.Exception.Message)" -ForegroundColor Red
  Add-Log "ERROR: $($_.Exception.Message)"
  Read-Host 'Enter para cerrar'
  exit 1
}
