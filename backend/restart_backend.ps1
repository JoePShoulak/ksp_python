$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = "C:\Users\joeps\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$port = 5000
$runtimeDir = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) ".runtime"
$pythonDeps = Join-Path $repo ".python-deps"

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

$stdoutLog = Join-Path $runtimeDir "backend.stdout.log"
$stderrLog = Join-Path $runtimeDir "backend.stderr.log"
$command = "set PYTHONPATH=$pythonDeps&& `"$python`" backend\main.py > `"$stdoutLog`" 2> `"$stderrLog`""

$backendProcess = Start-Process `
  -FilePath "cmd.exe" `
  -ArgumentList @("/d", "/s", "/c", $command) `
  -WorkingDirectory $repo `
  -WindowStyle Hidden `
  -PassThru

Set-Content -Path (Join-Path $runtimeDir "backend.pid") -Value $backendProcess.Id

Start-Sleep -Seconds 2
Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/status"
