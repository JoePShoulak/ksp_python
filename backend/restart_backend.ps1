$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = "C:\Users\joeps\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$port = 5000

$listeners = @(
  Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
)

foreach ($processId in $listeners) {
  if ($processId) {
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
  }
}

Start-Sleep -Milliseconds 500
Start-Process `
  -FilePath $python `
  -ArgumentList @("backend\main.py") `
  -WorkingDirectory $repo `
  -WindowStyle Hidden

Start-Sleep -Seconds 2
Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/status"
