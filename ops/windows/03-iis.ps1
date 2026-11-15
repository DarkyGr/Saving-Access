<#
.SYNOPSIS
  Publishes the local Save-Pass installation through IIS on HTTPS (task 36):
  the site serves the built SPA from <install>\web and proxies /api to the API
  on 127.0.0.1 (rules and headers in the web.config written by the release).
.DESCRIPTION
  Port HTTPS_PORT (8443 by default; 443 is Savings Tool's site). Needs URL
  Rewrite 2.1 and ARR 3.0 (already installed for Savings Tool). Only adds what
  this site needs at server level (proxy on, allowed server variables) and
  never changes the Savings Tool site. IIS logs go to Backup\logs\iis.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File ops\windows\03-iis.ps1
#>
param(
    [string]$AppDir = 'Y:\Apps\Save-Pass',
    [string]$LogDir = ''
)
. "$PSScriptRoot\common.ps1"
Assert-Admin
if (-not $LogDir) { $LogDir = Join-Path $RepoDir 'Backup\logs\iis' }
Assert-NotOnC $LogDir 'The IIS log folder'

Write-Step 'Checking IIS'
foreach ($feature in 'IIS-WebServerRole', 'IIS-WebServer', 'IIS-CommonHttpFeatures', 'IIS-StaticContent', 'IIS-DefaultDocument', 'IIS-HttpErrors', 'IIS-HttpLogging', 'IIS-RequestFiltering', 'IIS-HttpCompressionStatic', 'IIS-ManagementConsole') {
    $state = Get-WindowsOptionalFeature -Online -FeatureName $feature
    if ($state.State -ne 'Enabled') { Enable-WindowsOptionalFeature -Online -FeatureName $feature -All -NoRestart | Out-Null }
}
if (-not (Test-Path "$env:SystemRoot\System32\inetsrv\rewrite.dll")) {
    throw 'Install IIS URL Rewrite 2.1 (https://www.iis.net/downloads/microsoft/url-rewrite) and run this script again.'
}
if (-not (Test-Path "$env:ProgramFiles\IIS\Application Request Routing\requestRouter.dll")) {
    throw 'Install IIS Application Request Routing 3.0 (https://www.iis.net/downloads/microsoft/application-request-routing) and run this script again.'
}
Import-Module WebAdministration

$settings = Read-EnvFile (Join-Path $AppDir '.env.production')
$port = [int]$settings['HTTPS_PORT']
$siteDir = Join-Path $AppDir 'web'
if (-not (Test-Path (Join-Path $siteDir 'web.config'))) { throw "Run the release first: $siteDir\web.config not found." }
$thumbprint = (Get-Content -LiteralPath (Join-Path $AppDir 'certs\thumbprint.txt')).Trim()
if (-not (Test-Path "Cert:\LocalMachine\My\$thumbprint")) { throw 'Certificate not found: run 02-certificate.ps1.' }

Write-Step 'ARR proxy on (keeps the original host); allowed server variables'
Set-WebConfigurationProperty -PSPath 'MACHINE/WEBROOT/APPHOST' -Filter 'system.webServer/proxy' -Name 'enabled' -Value 'True'
Set-WebConfigurationProperty -PSPath 'MACHINE/WEBROOT/APPHOST' -Filter 'system.webServer/proxy' -Name 'preserveHostHeader' -Value 'True'
foreach ($variable in 'HTTP_X_FORWARDED_PROTO', 'HTTP_X_CLIENT_IP') {
    $allowed = Get-WebConfiguration -PSPath 'MACHINE/WEBROOT/APPHOST' -Filter "system.webServer/rewrite/allowedServerVariables/add[@name='$variable']"
    if (-not $allowed) {
        Add-WebConfiguration -PSPath 'MACHINE/WEBROOT/APPHOST' -Filter 'system.webServer/rewrite/allowedServerVariables' -Value @{ name = $variable }
    }
}

Write-Step "Site '$SiteName' on https://*:$port"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
if (Get-Website -Name $SiteName) { Remove-Website -Name $SiteName }
# A previous certificate binding on this port (from an earlier run) is replaced.
& netsh http delete sslcert ipport=0.0.0.0:$port 2>&1 | Out-Null
New-Website -Name $SiteName -PhysicalPath $siteDir -Port $port -Ssl -IPAddress '*' | Out-Null
Get-WebBinding -Name $SiteName -Protocol https | ForEach-Object { $_.AddSslCertificate($thumbprint, 'My') }
Set-ItemProperty "IIS:\Sites\$SiteName" -Name logFile.directory -Value $LogDir
# IIS reads the static files; the app folder already grants Network Service (05-tasks).
& icacls $siteDir /grant 'IIS_IUSRS:(OI)(CI)RX' | Out-Null
Start-Website -Name $SiteName

Write-Done "IIS publishes Save-Pass: $($settings['APP_BASE_URL'])"
Write-Host 'Next: 04-network-power.ps1'
