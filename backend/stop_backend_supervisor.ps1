$backendDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$requestFile = Join-Path $backendDir ".stop-request"

Set-Content -Path $requestFile -Value (Get-Date -Format "o")
Write-Host "Backend supervisor stop requested."
