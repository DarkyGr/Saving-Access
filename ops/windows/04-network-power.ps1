<#
.SYNOPSIS
  Opens the Save-Pass HTTPS port only to the home network and keeps the laptop
  awake on power (task 36; same power settings as Savings Tool).
.DESCRIPTION
  Firewall: inbound TCP HTTPS_PORT (8443) allowed only on the Private profile
  (your home Wi-Fi must be marked Private). Power: plugged in, the laptop
  never sleeps and closing the lid does nothing; on battery nothing changes.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File ops\windows\04-network-power.ps1
#>
param(
    [string]$AppDir = 'Y:\Apps\Save-Pass',
    [string]$RuleName = 'Save-Pass HTTPS (home network)'
)
. "$PSScriptRoot\common.ps1"
Assert-Admin
$port = [int](Read-EnvFile (Join-Path $AppDir '.env.production'))['HTTPS_PORT']

Write-Step "Firewall: TCP $port, Private profile only"
Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -Protocol TCP -LocalPort $port -Profile Private -Action Allow | Out-Null
foreach ($p in Get-NetConnectionProfile) {
    if ($p.NetworkCategory -ne 'Private') { Write-Note "Network '$($p.Name)' is $($p.NetworkCategory): the phone will not reach the app on it." }
}

Write-Step 'Power: plugged in, never sleep; closing the lid does nothing'
& powercfg /change standby-timeout-ac 0
& powercfg /change hibernate-timeout-ac 0
& powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
& powercfg /setactive SCHEME_CURRENT

Write-Done 'Firewall rule and power settings ready.'
Write-Host 'Next: 05-tasks.ps1'
