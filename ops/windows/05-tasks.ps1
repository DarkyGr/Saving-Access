<#
.SYNOPSIS
  Scheduled tasks of the local Save-Pass installation (task 36), all under
  "\Save-Pass\" and run by the Network Service account:
    API           at startup (and restarted if it stops): uvicorn on 127.0.0.1.
    Backup        daily 02:30 (or as soon as possible if the laptop was off).
    Restore test  Sundays 03:30: restores the newest backup into a scratch database.
    Reminders     daily 08:05 and at startup: email verification reminders
                  (does nothing while EMAIL_VERIFICATION_ENABLED is off).
  Times are 30 min after Savings Tool's, so both never run at once.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File ops\windows\05-tasks.ps1
#>
param(
    [string]$AppDir = 'Y:\Apps\Save-Pass',
    [string]$BackupDir = ''
)
. "$PSScriptRoot\common.ps1"
Assert-Admin
if (-not $BackupDir) { $BackupDir = Join-Path $RepoDir 'Backup\db' }
Assert-NotOnC $BackupDir 'The backup folder'
$python = Join-Path $AppDir 'python\python.exe'
if (-not (Test-Path $python)) { throw 'Install the app first: python scripts\release.py --to Y:\Apps\Save-Pass' }

$envFile = Join-Path $AppDir '.env.production'
$settings = Read-EnvFile $envFile
$logs = Join-Path $AppDir 'logs'
$run = Join-Path $AppDir 'ops\run.py'
$appCode = Join-Path $AppDir 'app'
New-Item -ItemType Directory -Force -Path $logs, $BackupDir, (Join-Path $AppDir 'tmp') | Out-Null

Write-Step 'Folder rights for Network Service'
# Modify: the API writes its logs, temp files and Python caches here.
& icacls $AppDir /grant "${ServiceAccount}:(OI)(CI)M" | Out-Null
& icacls $BackupDir /grant "${ServiceAccount}:(OI)(CI)M" | Out-Null
# The settings hold the secrets: only administrators, the system and the service read them.
& icacls $envFile /inheritance:r /grant:r 'Administrators:F' 'SYSTEM:F' "${ServiceAccount}:R" | Out-Null

$principal = New-ScheduledTaskPrincipal -UserId $ServiceAccount -LogonType ServiceAccount -RunLevel Limited
function Register-SavePassTask([string]$Name, $Action, $Triggers, [switch]$Forever) {
    $taskSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
    if ($Forever) { $taskSettings.ExecutionTimeLimit = 'PT0S' } else { $taskSettings.ExecutionTimeLimit = 'PT1H' }
    Register-ScheduledTask -TaskPath $TaskFolder -TaskName $Name -Action $Action -Trigger $Triggers `
        -Principal $principal -Settings $taskSettings -Force | Out-Null
    Write-Done "Task $TaskFolder$Name"
}
# cmd /c so the output of each run is appended to a log file.
function New-PythonAction([string]$Arguments, [string]$Log) {
    New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\cmd.exe" `
        -Argument "/c `"`"$python`" $Arguments >> `"$Log`" 2>&1`"" -WorkingDirectory $AppDir
}

Write-Step 'Registering the tasks'
$apiArgs = "`"$run`" --env `"$envFile`" --cwd `"$appCode`" uvicorn app.main:app --host 127.0.0.1 --port $($settings['API_PORT'])"
$startup = New-ScheduledTaskTrigger -AtStartup
$startup.Delay = 'PT30S'
Register-SavePassTask 'API' (New-PythonAction $apiArgs (Join-Path $logs 'api.log')) @($startup) -Forever

$backupArgs = "`"$(Join-Path $AppDir 'ops\backup.py')`" --env `"$envFile`" --out `"$BackupDir`""
Register-SavePassTask 'Backup' (New-PythonAction $backupArgs (Join-Path $logs 'jobs.log')) @(New-ScheduledTaskTrigger -Daily -At '02:30')
$restoreArgs = "`"$(Join-Path $AppDir 'ops\restore_test.py')`" --env `"$envFile`" --dir `"$BackupDir`""
Register-SavePassTask 'Restore test' (New-PythonAction $restoreArgs (Join-Path $logs 'jobs.log')) @(New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At '03:30')
$reminderArgs = "`"$run`" --env `"$envFile`" --cwd `"$appCode`" app.cli send-verification-reminders"
$reminderStartup = New-ScheduledTaskTrigger -AtStartup
$reminderStartup.Delay = 'PT5M'
Register-SavePassTask 'Reminders' (New-PythonAction $reminderArgs (Join-Path $logs 'jobs.log')) @((New-ScheduledTaskTrigger -Daily -At '08:05'), $reminderStartup)

Write-Step 'Starting the API'
Start-ScheduledTask -TaskPath $TaskFolder -TaskName 'API'
$healthy = $false
for ($i = 0; $i -lt 30 -and -not $healthy; $i++) {
    Start-Sleep -Seconds 2
    try { $healthy = (Invoke-RestMethod "http://127.0.0.1:$($settings['API_PORT'])/api/health" -TimeoutSec 5).status -eq 'ok' } catch { }
}
if ($healthy) { Write-Done 'The API answers and reaches the database.' }
else { Write-Note "The API does not answer yet: check $logs\api.log" }
Write-Host "Open $($settings['APP_BASE_URL'])"
Write-Host 'Run a first backup now: Start-ScheduledTask -TaskPath "\Save-Pass\" -TaskName Backup'
