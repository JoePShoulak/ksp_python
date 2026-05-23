import Panel from "./Panel";

function StatusPanel({ apiStatus, isLoading, onRefresh }) {
  return (
    <Panel title="Backend Status">
      <p>{apiStatus}</p>

      <button onClick={onRefresh} disabled={isLoading}>
        Refresh Status
      </button>
    </Panel>
  );
}

export default StatusPanel;
