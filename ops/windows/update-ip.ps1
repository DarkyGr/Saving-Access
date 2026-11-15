<#
.SYNOPSIS
  Run it when the laptop's IP on the home network changes (task 36): updates
  TRUSTED_ORIGINS, makes a new certificate with the same authority, updates
  IIS and restarts the API. The phone keeps its authority: nothing to
  reinstall there.
.EXAMPLE
  Double click ops\windows\update-ip.cmd (it asks for administrator rights).
#>
param(
    [string]$AppDir = 'Y:\Apps\Save-Pass',
    [string]$Mkcert = 'Y:\Code\Claude\tools\mkcert.exe',
    [switch]$Force
)
. "$PSScriptRoot\common.ps1"

# The old LAN addresses leave the list; names and any other address stay.
function Set-LanOrigin([string]$Line, [string]$Ip, [string]$Port) {
    $value = $Line -replace '^\s*TRUSTED_ORIGINS\s*=\s*', ''
    $kept = @($value.Trim('"') -split ',' | ForEach-Object { $_.Trim() } | Where-Object {
            $_ -and $_ -notmatch '^https://(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)'
        })
    return 'TRUSTED_ORIGINS=' + ((@("https://${Ip}:$Port") + $kept) -join ',')
}

try {
    Assert-Admin
    $config = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } |
        Select-Object -First 1
    if (-not $config) { throw 'This laptop is not connected to a network.' }
    $ip = $config.IPv4Address.IPAddress
    Write-Step "Current IP: $ip ($($config.InterfaceAlias))"

    $envFile = Join-Path $AppDir '.env.production'
    $settings = Read-EnvFile $envFile
    $port = $settings['HTTPS_PORT']
    $lines = @(Get-Content -LiteralPath $envFile)
    $index = -1
    for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i] -match '^\s*TRUSTED_ORIGINS\s*=') { $index = $i } }
    if ($index -lt 0) { throw 'TRUSTED_ORIGINS is not in the settings file.' }

    $thumbFile = Join-Path $AppDir 'certs\thumbprint.txt'
    $oldThumb = if (Test-Path -LiteralPath $thumbFile) { (Get-Content -LiteralPath $thumbFile).Trim() } else { '' }
    if ($lines[$index] -match [regex]::Escape("https://${ip}:$port") -and $oldThumb -and -not $Force) {
        Write-Done 'The IP did not change: nothing to do.'
    } else {
        $lines[$index] = Set-LanOrigin $lines[$index] $ip $port
        [IO.File]::WriteAllLines($envFile, [string[]]$lines)

        Write-Step 'New certificate'
        & "$PSScriptRoot\02-certificate.ps1" -Mkcert $Mkcert -Ip $ip -AppDir $AppDir
        Write-Step 'Updating IIS'
        & "$PSScriptRoot\03-iis.ps1" -AppDir $AppDir

        $newThumb = (Get-Content -LiteralPath $thumbFile).Trim()
        if ($oldThumb -and $oldThumb -ne $newThumb -and (Test-Path "Cert:\LocalMachine\My\$oldThumb")) {
            Remove-Item "Cert:\LocalMachine\My\$oldThumb"
        }

        Write-Step 'Restarting the API'
        $task = Get-ScheduledTask -TaskPath $TaskFolder -TaskName 'API' -ErrorAction SilentlyContinue
        if ($task) {
            Stop-ScheduledTask -TaskPath $TaskFolder -TaskName 'API'
            $listener = Get-NetTCPConnection -LocalPort ([int]$settings['API_PORT']) -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($listener) { Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue }
            Start-ScheduledTask -TaskPath $TaskFolder -TaskName 'API'
        }
        Write-Done "Ready: https://${ip}:$port"
    }
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
}
Read-Host 'Enter para cerrar' | Out-Null
