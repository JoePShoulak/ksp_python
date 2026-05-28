$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = "C:\Users\joeps\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$port = 5000
$runtimeDir = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) ".runtime"
$freshPythonDeps = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) ".codex_deps_fresh"
$runtimePythonDeps = Join-Path $runtimeDir "python-deps"
$repoPythonDeps = Join-Path $repo ".python-deps"
$pythonDeps = if (Test-Path $freshPythonDeps) { $freshPythonDeps } elseif (Test-Path $runtimePythonDeps) { $runtimePythonDeps } else { $repoPythonDeps }

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

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

$env:PYTHONPATH = $pythonDeps
$backendProcess = Start-Process `
  -FilePath $python `
  -ArgumentList @("backend\main.py") `
  -WorkingDirectory $repo `
  -WindowStyle Hidden `
  -PassThru

Set-Content -Path (Join-Path $runtimeDir "backend.pid") -Value $backendProcess.Id

Start-Sleep -Seconds 2
Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/status"
