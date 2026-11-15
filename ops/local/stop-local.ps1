# Takes down what start-local.ps1 brought up: its timer, the containers and
# Docker if the script opened it. Data (the volume) and images stay.
# With -RunId it is the timer of a run: it waits and stops only that run.
param([string]$RunId = '', [switch]$NoPause)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'local-common.ps1')

try {
  if ($RunId) {
    # By the clock, in short naps: sleeping the laptop must not extend the time.
    while ($true) {
      $current = Read-State
      if (-not $current -or $current.runId -ne $RunId) { exit 0 }
      if ((Get-Date) -ge [datetime]$current.stopAt) { break }
      Start-Sleep -Seconds 15
    }
    Add-Log 'auto stop'
  }

  $state = Read-State
  if ($state -and $state.watchdogPid -and $state.watchdogPid -ne $PID -and (Get-ProcessInfo $state.watchdogPid)) {
    Stop-Tree $state.watchdogPid
  }
  Stop-Containers
  if ($state -and $state.startedDocker) { Stop-DockerDesktop }
  if (Test-Path $StateFile) { Remove-Item $StateFile -Force }
  Write-Step 'Todo apagado.'
  if (-not $RunId -and -not $NoPause) { Start-Sleep -Seconds 3 }
} catch {
  Add-Log "ERROR: $($_.Exception.Message)"
  if ($RunId -or $NoPause) { exit 1 }
  Write-Host "[Save-Pass] ERROR: $($_.Exception.Message)" -ForegroundColor Red
  Read-Host 'Enter para cerrar'
  exit 1
}
