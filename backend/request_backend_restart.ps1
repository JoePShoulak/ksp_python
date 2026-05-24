$backendDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$requestFile = Join-Path $backendDir ".restart-request"

Set-Content -Path $requestFile -Value (Get-Date -Format "o")
Write-Host "Backend restart requested."
