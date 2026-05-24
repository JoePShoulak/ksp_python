import Panel from "./Panel";

function ActionsPanel({ actions, activeActionId, isLoading, onRunAction }) {
  return (
    <Panel title="Mission Controls">
      <div className="actions-panel">
        {actions.map(action => {
          const isActive = action.id === activeActionId;

          return (
            <button
              key={action.id}
              className={`action-button ${isActive ? "is-running" : ""}`}
              onClick={() => onRunAction(action.id)}
              disabled={isLoading}
              aria-busy={isActive}>
              <span>{action.label}</span>
              {isActive && <span className="action-state">Running</span>}
            </button>
          );
        })}
      </div>
    </Panel>
  );
}

export default ActionsPanel;
