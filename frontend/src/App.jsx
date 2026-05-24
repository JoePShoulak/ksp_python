import { useEffect, useState } from "react";
import "./styles/app-shell.css";
import "./styles/panels.css";
import "./styles/telemetry.css";
import "./styles/responsive.css";

import { ACTIONS } from "./data/actions";
import { getTelemetry, runKspAction } from "./api/kspApi";

import ActionsPanel from "./components/ActionsPanel";
import VisDatPanel from "./components/VisDatPanel";

function App() {
  const [telemetry, setTelemetry] = useState(null);
  const [hasVessel, setHasVessel] = useState(false);
  const [connectionState, setConnectionState] = useState("connecting");
  const [activeActionId, setActiveActionId] = useState(null);
  const [lastActionMessage, setLastActionMessage] = useState("");

  const isActionRunning = activeActionId !== null;

  async function pollTelemetry() {
    try {
      const data = await getTelemetry();

      setTelemetry(data.telemetry ?? null);
      setHasVessel(Boolean(data.has_vessel));
      setConnectionState(data.has_vessel ? "live" : "idle");
    } catch {
      setTelemetry(null);
      setHasVessel(false);
      setConnectionState("offline");
    }
  }

  async function handleRunAction(actionId) {
    setActiveActionId(actionId);
    setLastActionMessage("");

    try {
      const data = await runKspAction(actionId);

      setLastActionMessage(data.message ?? "Action started");
      await pollTelemetry();
    } catch (error) {
      setLastActionMessage(error.message);
    } finally {
      setActiveActionId(null);
    }
  }

  useEffect(() => {
    const initialPollId = window.setTimeout(pollTelemetry, 0);

    const intervalMs = hasVessel ? 250 : 1500;
    const intervalId = setInterval(pollTelemetry, intervalMs);

    return () => {
      clearTimeout(initialPollId);
      clearInterval(intervalId);
    };
  }, [hasVessel]);

  return (
    <main className="app">
      <header className="app-header">
        <div>
          <p className="eyebrow">KSP Control Panel</p>
          <h1>Mission Dashboard</h1>
        </div>

        <div className={`connection-pill ${connectionState}`}>
          <span className="connection-dot" />
          {connectionState === "live" && "Vessel linked"}
          {connectionState === "idle" && "Waiting for vessel"}
          {connectionState === "offline" && "Backend offline"}
          {connectionState === "connecting" && "Connecting"}
        </div>
      </header>

      {lastActionMessage && (
        <section className="action-toast">{lastActionMessage}</section>
      )}

      <section className="dashboard-grid">
        <ActionsPanel
          actions={ACTIONS}
          isLoading={isActionRunning}
          onRunAction={handleRunAction}
        />

        <VisDatPanel telemetry={telemetry} hasVessel={hasVessel} />
      </section>
    </main>
  );
}

export default App;
