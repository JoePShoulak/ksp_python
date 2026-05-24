import { useCallback, useEffect, useRef, useState } from "react";
import "./styles/app-shell.css";
import "./styles/panels.css";
import "./styles/telemetry.css";
import "./styles/responsive.css";

import { ACTIONS } from "./data/actions";
import { cycleCamera, getTelemetry, runKspAction } from "./api/kspApi";

import ActionsPanel from "./components/ActionsPanel";
import VisDatPanel from "./components/VisDatPanel";

function App() {
  const [telemetry, setTelemetry] = useState(null);
  const [hasVessel, setHasVessel] = useState(false);
  const [connectionState, setConnectionState] = useState("connecting");
  const [activeActionId, setActiveActionId] = useState(null);
  const [lastActionMessage, setLastActionMessage] = useState("");
  const [isCyclingCamera, setIsCyclingCamera] = useState(false);
  const hasVesselRef = useRef(hasVessel);
  const isPollingRef = useRef(false);

  const isActionRunning = activeActionId !== null;

  useEffect(() => {
    hasVesselRef.current = hasVessel;
  }, [hasVessel]);

  const pollTelemetry = useCallback(async (options = {}) => {
    try {
      const data = await getTelemetry(options);
      const hasActiveVessel = Boolean(data.has_vessel);

      setTelemetry(hasActiveVessel ? (data.telemetry ?? null) : null);
      setHasVessel(hasActiveVessel);
      setConnectionState(hasActiveVessel ? "live" : "idle");
    } catch (error) {
      if (error.name === "AbortError") {
        return;
      }

      setTelemetry(null);
      setHasVessel(false);
      setConnectionState("offline");
    }
  }, []);

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

  async function handleCycleCamera() {
    setIsCyclingCamera(true);
    setLastActionMessage("");

    try {
      const data = await cycleCamera();

      setTelemetry(previousTelemetry => {
        if (!previousTelemetry) {
          return previousTelemetry;
        }

        return {
          ...previousTelemetry,
          cameras: data.cameras,
        };
      });
    } catch (error) {
      setLastActionMessage(error.message);
    } finally {
      setIsCyclingCamera(false);
    }
  }

  useEffect(() => {
    let isMounted = true;
    let timeoutId = null;

    async function runPoll() {
      if (!isMounted) {
        return;
      }

      if (!isPollingRef.current) {
        isPollingRef.current = true;

        try {
          await pollTelemetry();
        } finally {
          isPollingRef.current = false;
        }
      }

      const intervalMs = hasVesselRef.current ? 1000 : 2000;
      timeoutId = window.setTimeout(runPoll, intervalMs);
    }

    runPoll();

    return () => {
      isMounted = false;

      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [pollTelemetry]);

  return (
    <main className="app">
      <header className="app-header">
        <div>
          <p className="eyebrow">KSP Control Panel</p>
          <h1>Mission Dashboard</h1>
        </div>

        <div className={`connection-pill ${connectionState}`} aria-live="polite">
          <span className="connection-dot" />
          {connectionState === "live" && "Vessel linked"}
          {connectionState === "idle" && "Waiting for vessel"}
          {connectionState === "offline" && "Backend offline"}
          {connectionState === "connecting" && "Connecting"}
        </div>
      </header>

      {lastActionMessage && (
        <section className="action-toast" aria-live="polite">
          {lastActionMessage}
        </section>
      )}

      <section className="dashboard-grid">
        <ActionsPanel
          actions={ACTIONS}
          activeActionId={activeActionId}
          isLoading={isActionRunning}
          onRunAction={handleRunAction}
        />

        <VisDatPanel
          telemetry={telemetry}
          hasVessel={hasVessel}
          isCyclingCamera={isCyclingCamera}
          onCycleCamera={handleCycleCamera}
        />
      </section>
    </main>
  );
}

export default App;
