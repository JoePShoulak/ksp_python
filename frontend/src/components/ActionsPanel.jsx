import Panel from "./Panel";

function ActionButton({ action, activeActionId, isLoading, onRunAction }) {
  const isActive = action.id === activeActionId;

  return (
    <button
      className={`action-button ${isActive ? "is-running" : ""}`}
      onClick={() => onRunAction(action.id)}
      disabled={isLoading}
      aria-busy={isActive}>
      <span>{action.label}</span>
      {isActive && <span className="action-state">Running</span>}
    </button>
  );
}

function ActionsPanel({ actions, activeActionId, isLoading, onRunAction }) {
  const missionSteps = actions.filter(action => action.section !== "sequence");
  const sequences = actions.filter(action => action.section === "sequence");

  return (
    <Panel title="Mission Controls">
      <div className="actions-panel">
        <div className="action-group">
          {missionSteps.map(action => (
            <ActionButton
              key={action.id}
              action={action}
              activeActionId={activeActionId}
              isLoading={isLoading}
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
                onRunAction={onRunAction}
              />
            ))}
          </div>
        )}
      </div>
    </Panel>
  );
}

export default ActionsPanel;
