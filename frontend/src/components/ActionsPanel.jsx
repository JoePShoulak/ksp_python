import Panel from "./Panel";

function ActionsPanel({ actions, isLoading, onRunAction }) {
  return (
    <Panel title="Mission Controls">
      <div className="actions-panel">
        {actions.map(action => (
          <button
            key={action.id}
            className="action-button"
            onClick={() => onRunAction(action.id)}
            disabled={isLoading}>
            {action.label}
          </button>
        ))}
      </div>
    </Panel>
  );
}

export default ActionsPanel;
