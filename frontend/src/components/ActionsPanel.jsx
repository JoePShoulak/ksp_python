import Panel from "./Panel";
import BackendHealthPanel from "./BackendHealthPanel";

function ActionButton({
  action,
  activeActionId,
  missionLocked,
  missionOptions,
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
      onClick={() => onRunAction(action.id, missionOptions)}
      disabled={isDisabled}
      aria-busy={isActive || isPending}>
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
  backendHealth,
  connectionState,
  missionOptions,
  missionActive,
  pendingActionId,
  onReleaseAction,
  onMissionOptionChange,
  onRevertToLaunch,
  onRunAction,
  allowPopout = true,
}) {
  const missionSteps = actions.filter(action => action.section !== "sequence");
  const sequences = actions.filter(action => action.section === "sequence");
  const missionLocked = missionActive || Boolean(activeActionId);
  const vesselLinked = connectionState === "live";
  const canReleaseMission = missionLocked || Boolean(pendingActionId);
  const canRevertMission = vesselLinked || missionLocked || Boolean(pendingActionId);
  const showBackendDebug = false;

  return (
    <div className="actions-column">
      <Panel
        title={<MissionPanelTitle connectionState={connectionState} />}
        popout={allowPopout}
        popoutName="Missions">
        <div className="actions-panel">
          <div className="action-group">
            {missionSteps.map(action => (
              <ActionButton
                key={action.id}
                action={action}
                activeActionId={activeActionId}
                missionLocked={missionLocked}
                missionOptions={missionOptions}
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
                  missionOptions={missionOptions}
                  pendingActionId={pendingActionId}
                  vesselLinked={vesselLinked}
                  onRunAction={onRunAction}
                />
              ))}
            </div>
          )}

          <div className="mission-options" aria-label="LKO tourism options">
            <label className="mission-option">
              <input
                type="checkbox"
                checked={missionOptions.revertOnFailure}
                onChange={event =>
                  onMissionOptionChange("revertOnFailure", event.target.checked)
                }
                disabled={missionLocked || Boolean(pendingActionId)}
              />
              <span>Revert on Failure</span>
            </label>

            <label className="mission-option">
              <input
                type="checkbox"
                checked={missionOptions.retryOnRevert}
                onChange={event =>
                  onMissionOptionChange("retryOnRevert", event.target.checked)
                }
                disabled={
                  missionLocked ||
                  Boolean(pendingActionId) ||
                  !missionOptions.revertOnFailure
                }
              />
              <span>Retry on Revert</span>
            </label>
          </div>

          {actionError && (
            <p className="action-error" role="status">
              {actionError}
            </p>
          )}

          <div className="mission-release">
            <button
              className="revert-button"
              type="button"
              onClick={onRevertToLaunch}
              disabled={!canRevertMission}>
              Revert to Launch
            </button>
            <button
              className="release-button"
              type="button"
              onClick={onReleaseAction}
              disabled={!canReleaseMission}>
              Release Mission
            </button>
          </div>
        </div>
      </Panel>

      {/* Keep this debug card available for troubleshooting backend/API health. */}
      {showBackendDebug && (
        <Panel title="Backend" popout={false}>
          <BackendHealthPanel backendHealth={backendHealth} />
        </Panel>
      )}

    </div>
  );
}

export default ActionsPanel;
