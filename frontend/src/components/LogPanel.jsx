import Panel from "./Panel";

function LogPanel({ log }) {
  return (
    <Panel title="Log">
      {log.length === 0 ? (
        <p>No log entries yet.</p>
      ) : (
        <ul className="log">
          {log.map(entry => (
            <li key={entry.id}>
              <span className="timestamp">{entry.timestamp}</span>
              <span>{entry.message}</span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

export default LogPanel;
