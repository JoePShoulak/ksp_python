import Panel from "./Panel";

function ResponsePanel({ lastResponse }) {
  return (
    <Panel title="Last Response">
      {lastResponse ? (
        <pre>{JSON.stringify(lastResponse, null, 2)}</pre>
      ) : (
        <p>No response yet.</p>
      )}
    </Panel>
  );
}

export default ResponsePanel;
