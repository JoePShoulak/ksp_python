function BackendHealthPanel({ backendHealth }) {
  const checkedAt = backendHealth.checkedAt
    ? new Date(backendHealth.checkedAt).toLocaleTimeString([], {
        hour: "numeric",
        minute: "2-digit",
        second: "2-digit",
      })
    : "Not checked yet";
  const uptime = formatDuration(backendHealth.data?.uptime_seconds);
  const pid = backendHealth.data?.pid;
  const action = backendHealth.data?.action;
  const statusLabel = {
    online: "Backend online",
    offline: "Backend unreachable",
    checking: "Checking backend",
    busy: "Backend busy",
  }[backendHealth.state] ?? "Checking backend";

  return (
    <div className="backend-health">
      <div className={`backend-health-status ${backendHealth.state}`}>
        <span className="connection-dot" />
        <strong>{statusLabel}</strong>
      </div>

      <div className="backend-health-details">
        <div>
          <span>Checked</span>
          <strong>{checkedAt}</strong>
        </div>
        <div>
          <span>Uptime</span>
          <strong>{uptime}</strong>
        </div>
        <div>
          <span>Process</span>
          <strong>{pid ? `PID ${pid}` : "Unknown"}</strong>
        </div>
        <div>
          <span>Action</span>
          <strong>{action ?? "None"}</strong>
        </div>
      </div>

      {backendHealth.state === "offline" && (
        <p className="backend-health-note">Restart ksp-backend if this stays offline.</p>
      )}

      <a className="backend-health-link" href="/api/health" target="_blank" rel="noreferrer">
        Open health
      </a>
    </div>
  );
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds)) {
    return "Unknown";
  }

  const totalSeconds = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }

  return `${minutes}m`;
}

export default BackendHealthPanel;
