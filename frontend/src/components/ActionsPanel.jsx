import Panel from "./Panel";

function ActionButton({
  action,
  activeActionId,
  missionLocked,
  pendingActionId,
  vesselLinked,
  onRunAction,
}) {
  const isActive = action.id === activeActionId;
  const isPending = action.id === pendingActionId;
  const isDisabled = !vesselLinked || Boolean(pendingActionId) || missionLocked;

  return (
    <button
      className={`action-button ${isActive ? "is-running" : ""}`}
      onClick={() => onRunAction(action.id)}
      disabled={isDisabled}
      aria-busy={isActive || isPending}>
      <span>{action.label}</span>
      {isPending && <span className="action-state">Starting</span>}
      {isActive && <span className="action-state">Running</span>}
    </button>
  );
}

function MissionPanelTitle({ connectionState }) {
  const connectionLabel = {
    live: "Vessel linked",
    idle: "Waiting for vessel",
    offline: "Backend offline",
    connecting: "Connecting",
  }[connectionState] ?? "Connecting";

  return (
    <span className="panel-title-row">
      <span>Missions</span>
      <span className={`connection-pill ${connectionState}`} aria-live="polite">
        <span className="connection-dot" />
        {connectionLabel}
      </span>
    </span>
  );
}

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

function ActionsPanel({
  actions,
  activeActionId,
  actionError,
  backendHealth,
  connectionState,
  missionActive,
  pendingActionId,
  onAbortAction,
  onRunAction,
}) {
  const missionSteps = actions.filter(action => action.section !== "sequence");
  const sequences = actions.filter(action => action.section === "sequence");
  const missionLocked = missionActive || Boolean(activeActionId);
  const vesselLinked = connectionState === "live";
  const canAbortMission = missionLocked || Boolean(pendingActionId);
  const showBackendDebug = false;

  return (
    <div className="actions-column">
      <Panel title={<MissionPanelTitle connectionState={connectionState} />}>
        <div className="actions-panel">
          <div className="action-group">
            {missionSteps.map(action => (
              <ActionButton
                key={action.id}
                action={action}
                activeActionId={activeActionId}
                missionLocked={missionLocked}
                pendingActionId={pendingActionId}
                vesselLinked={vesselLinked}
                onRunAction={onRunAction}
              />
            ))}
          </div>

          {sequences.length > 0 && (
            <div className="action-group action-group-sequence">
              {sequences.map(action => (
                <ActionButton
                  key={action.id}
                  action={action}
                  activeActionId={activeActionId}
                  missionLocked={missionLocked}
                  pendingActionId={pendingActionId}
                  vesselLinked={vesselLinked}
                  onRunAction={onRunAction}
                />
              ))}
            </div>
          )}

          {actionError && (
            <p className="action-error" role="status">
              {actionError}
            </p>
          )}
        </div>
      </Panel>

      {/* Keep this debug card available for troubleshooting backend/API health. */}
      {showBackendDebug && (
        <Panel title="Backend">
          <BackendHealthPanel backendHealth={backendHealth} />
        </Panel>
      )}

      <Panel title="Abort">
        <button
          className="abort-button"
          type="button"
          onClick={onAbortAction}
          disabled={!canAbortMission}>
          Abort Mission
        </button>
      </Panel>
    </div>
  );
}

export default ActionsPanel;
