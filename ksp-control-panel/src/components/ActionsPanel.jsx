import Panel from "./Panel";

function ActionsPanel({ actions, isLoading, onRunAction }) {
  return (
    <Panel title="Actions">
      <div className="button-row">
        {actions.map(action => (
          <button
            key={action.id}
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
