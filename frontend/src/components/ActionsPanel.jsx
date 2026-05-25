import Panel from "./Panel";

function ActionButton({ action, activeActionId, isLoading, missionActive, onRunAction }) {
  const isActive = action.id === activeActionId;
  const isDisabled = isLoading || missionActive;

  return (
    <button
      className={`action-button ${isActive ? "is-running" : ""}`}
      onClick={() => onRunAction(action.id)}
      disabled={isDisabled}
      aria-busy={isActive}>
      <span>{action.label}</span>
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

function ActionsPanel({
  actions,
  activeActionId,
  actionError,
  connectionState,
  isLoading,
  missionActive,
  onAbortAction,
  onRunAction,
}) {
  const missionSteps = actions.filter(action => action.section !== "sequence");
  const sequences = actions.filter(action => action.section === "sequence");

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
                isLoading={isLoading}
                missionActive={missionActive}
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
                  isLoading={isLoading}
                  missionActive={missionActive}
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

      <Panel title="Abort">
        <button
          className="abort-button"
          type="button"
          onClick={onAbortAction}
          disabled={connectionState !== "live"}>
          Abort Vessel
        </button>
      </Panel>
    </div>
  );
}

export default ActionsPanel;
