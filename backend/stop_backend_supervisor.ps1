$backendDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtimeDir = Join-Path $backendDir ".runtime"
$requestFile = Join-Path $runtimeDir ".stop-request"

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
Set-Content -Path $requestFile -Value (Get-Date -Format "o")
Write-Host "Backend supervisor stop requested."
