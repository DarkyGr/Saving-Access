<#
.SYNOPSIS
  HTTPS certificate of the local Save-Pass installation (task 36) with mkcert,
  imported for IIS.
.DESCRIPTION
  By default it uses Savings Tool's mkcert authority
  (Y:\Code\Git\Repos\Savings-Tool\Backup\certs): this machine and the phone
  already trust it, so nothing new has to be installed on the phone. Without
  it, a new authority is made in this project's Backup\certs (access only for
  administrators) and Backup\certs\rootCA.pem must be installed on the phone.
  Names: the host of APP_BASE_URL, the hosts of TRUSTED_ORIGINS, the LAN IP,
  localhost and 127.0.0.1.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File ops\windows\02-certificate.ps1 -Ip 192.168.1.50
#>
param(
    [string]$Mkcert = 'Y:\Code\Claude\tools\mkcert.exe',
    [string]$Ip = '',
    [string]$AppDir = 'Y:\Apps\Save-Pass',
    [string]$CaRoot = ''
)
. "$PSScriptRoot\common.ps1"
Assert-Admin
$CaRoot = Get-CaRoot $CaRoot
Assert-NotOnC $CaRoot 'The certificate authority folder'
if (-not (Test-Path $Mkcert)) { throw "mkcert not found: $Mkcert" }

$settings = Read-EnvFile (Join-Path $AppDir '.env.production')
$names = New-Object System.Collections.Generic.List[string]
$names.Add(([Uri]$settings['APP_BASE_URL']).Host)
foreach ($origin in ("$($settings['TRUSTED_ORIGINS'])" -split ',')) {
    if ($origin.Trim()) { $names.Add(([Uri]$origin.Trim()).Host) }
}
if ($Ip) { $names.Add($Ip) }
$names.Add('localhost'); $names.Add('127.0.0.1')
$names = $names | Select-Object -Unique

$newAuthority = -not (Test-Path -LiteralPath (Join-Path $CaRoot 'rootCA.pem'))
New-Item -ItemType Directory -Force -Path $CaRoot | Out-Null
$certDir = Join-Path $AppDir 'certs'
New-Item -ItemType Directory -Force -Path $certDir | Out-Null
$env:CAROOT = $CaRoot

Write-Step "Authority in $CaRoot (trusted by this machine)"
& $Mkcert -install
if ($LASTEXITCODE -ne 0) { throw 'mkcert -install failed.' }
if ($newAuthority) {
    # Only administrators and the system can read the authority's key.
    & icacls $CaRoot /inheritance:r /grant:r 'Administrators:(OI)(CI)F' 'SYSTEM:(OI)(CI)F' | Out-Null
}

Write-Step "Certificate for: $($names -join ', ')"
$p12 = Join-Path $certDir 'savepass.p12'
& $Mkcert -pkcs12 -p12-file $p12 @names
if ($LASTEXITCODE -ne 0) { throw 'mkcert failed.' }
# mkcert protects PKCS#12 files with its fixed password "changeit".
$secure = ConvertTo-SecureString 'changeit' -AsPlainText -Force
$cert = Import-PfxCertificate -FilePath $p12 -CertStoreLocation Cert:\LocalMachine\My -Password $secure
Remove-Item -LiteralPath $p12 -Force
$cert.FriendlyName = 'Save-Pass (local)'
Set-Content -LiteralPath (Join-Path $certDir 'thumbprint.txt') -Value $cert.Thumbprint -Encoding ascii

Write-Done "Certificate $($cert.Thumbprint), valid until $($cert.NotAfter.ToString('yyyy-MM-dd'))."
if ($newAuthority) { Write-Note "New authority: install $(Join-Path $CaRoot 'rootCA.pem') on the phone as a trusted certificate." }
else { Write-Host 'The phone already trusts this authority (Savings Tool): nothing to install there.' }
Write-Host 'Next: 03-iis.ps1'
