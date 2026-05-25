param(
  [Parameter(Position = 0)]
  [ValidateSet(
    "status",
    "health",
    "up",
    "down",
    "restart",
    "reload",
    "logs",
    "deploy",
    "update",
    "ssh"
  )]
  [string]$Command = "status",

  [string]$HostName = "ksp@192.168.20.105",
  [string]$ProdUrl = "http://192.168.20.105:5173",
  [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"

function Invoke-ProdSsh {
  param([string]$RemoteCommand)
  ssh $HostName $RemoteCommand
}

function Show-Health {
  try {
    $health = Invoke-RestMethod -Uri "$ProdUrl/api/health" -TimeoutSec 5
    $backend = if ($health.ok) { "online" } else { "not ok" }
    $mission = if ($health.mission_active) { "active" } else { "idle" }
    $action = if ($health.action) { $health.action } else { "none" }
    $vessel = if ($health.cached_vessel_name) { $health.cached_vessel_name } else { "none" }
    $telemetryAge = if ($null -ne $health.telemetry_cache_age) {
      "{0:n1}s" -f [double]$health.telemetry_cache_age
    } else {
      "unknown"
    }
    $krpcOpen = if ($health.krpc_connections) {
      $health.krpc_connections.open_count
    } else {
      "unknown"
    }

    Write-Host "Backend:        $backend"
    Write-Host "Mission:        $mission"
    Write-Host "Action:         $action"
    Write-Host "Vessel:         $vessel"
    Write-Host "Telemetry age:  $telemetryAge"
    Write-Host "kRPC streams:   $krpcOpen open"
    Write-Host "Uptime:         $([int]$health.uptime_seconds)s"
  } catch {
    Write-Host "Backend health is unreachable at $ProdUrl/api/health"
    Write-Host $_.Exception.Message
    exit 1
  }
}

switch ($Command) {
  "status" {
    Write-Host "Production health"
    Show-Health
    Write-Host ""
    Write-Host "Backend service"
    Invoke-ProdSsh "systemctl --no-pager --full status ksp-backend || true"
  }
  "health" {
    Show-Health
  }
  "up" {
    Invoke-ProdSsh "sudo systemctl start ksp-backend && sudo nginx -t && sudo systemctl reload nginx"
    Show-Health
  }
  "down" {
    Invoke-ProdSsh "sudo systemctl stop ksp-backend"
    Write-Host "Backend stopped. The frontend may still load, but API calls will be offline."
  }
  "restart" {
    Invoke-ProdSsh "sudo systemctl restart ksp-backend"
    Show-Health
  }
  "reload" {
    Invoke-ProdSsh "sudo nginx -t && sudo systemctl reload nginx"
    Write-Host "Nginx reloaded."
  }
  "logs" {
    Invoke-ProdSsh "sudo journalctl -u ksp-backend -n 120 -f"
  }
  "deploy" {
    git push prod "HEAD:$Branch"
  }
  "update" {
    git push prod "HEAD:$Branch"
  }
  "ssh" {
    ssh $HostName
  }
}
