param(
  [int]$Port = 5000,
  [int]$PollSeconds = 1,
  [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

$backendDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $backendDir
$restartRequest = Join-Path $backendDir ".restart-request"
$stopRequest = Join-Path $backendDir ".stop-request"
$pidFile = Join-Path $backendDir ".backend.pid"
$logFile = Join-Path $backendDir ".backend-supervisor.log"
$stdoutLog = Join-Path $backendDir ".backend.stdout.log"
$stderrLog = Join-Path $backendDir ".backend.stderr.log"
$backendProcess = $null

function Write-SupervisorLog {
  param([string]$Message)

  $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  $line = "[$timestamp] $Message"
  Write-Host $line
  Add-Content -Path $logFile -Value $line
}

function Resolve-Python {
  if (Test-Path $Python) {
    return $Python
  }

  $resolved = Get-Command $Python -ErrorAction SilentlyContinue
  if ($resolved) {
    return $resolved.Source
  }

  return $Python
}

function Stop-PortListeners {
  $listeners = @(
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
      Select-Object -ExpandProperty OwningProcess -Unique
  )

  foreach ($processId in $listeners) {
    if ($processId) {
      Write-SupervisorLog "Stopping existing listener on port $Port (PID $processId)"
      Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
  }
}

function Stop-Backend {
  if ($script:backendProcess -and -not $script:backendProcess.HasExited) {
    Write-SupervisorLog "Stopping backend PID $($script:backendProcess.Id)"
    Stop-Process -Id $script:backendProcess.Id -Force -ErrorAction SilentlyContinue
    $script:backendProcess.WaitForExit(3000) | Out-Null
  }

  $script:backendProcess = $null
  Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

function Start-Backend {
  Stop-PortListeners

  $pythonExe = Resolve-Python
  Write-SupervisorLog "Starting backend with $pythonExe"

  $script:backendProcess = Start-Process `
    -FilePath $pythonExe `
    -ArgumentList @("backend\main.py") `
    -WorkingDirectory $repo `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

  Set-Content -Path $pidFile -Value $script:backendProcess.Id
  Write-SupervisorLog "Backend started on port $Port (PID $($script:backendProcess.Id))"
}

function Restart-Backend {
  param([string]$Reason = "Restart requested")

  Write-SupervisorLog $Reason
  Stop-Backend
  Start-Sleep -Milliseconds 500
  Start-Backend
}

Remove-Item -LiteralPath $restartRequest -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $stopRequest -Force -ErrorAction SilentlyContinue

try {
  Start-Backend
  Write-SupervisorLog "Watching $restartRequest"

  while ($true) {
    if ($script:backendProcess -and $script:backendProcess.HasExited) {
      Restart-Backend "Backend exited unexpectedly; restarting"
    }

    if (Test-Path $restartRequest) {
      Remove-Item -LiteralPath $restartRequest -Force -ErrorAction SilentlyContinue
      Restart-Backend "Restart request file detected"
    }

    if (Test-Path $stopRequest) {
      Remove-Item -LiteralPath $stopRequest -Force -ErrorAction SilentlyContinue
      Write-SupervisorLog "Stop request file detected"
      break
    }

    Start-Sleep -Seconds $PollSeconds
  }
}
finally {
  Stop-Backend
  Write-SupervisorLog "Supervisor stopped"
}
