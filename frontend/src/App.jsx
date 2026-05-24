import { useCallback, useEffect, useRef, useState } from "react";
import "./styles/app-shell.css";
import "./styles/panels.css";
import "./styles/telemetry.css";
import "./styles/responsive.css";

import { ACTIONS } from "./data/actions";
import {
  abortKspAction,
  getMissionStatus,
  getTelemetry,
  runKspAction,
} from "./api/kspApi";

import ActionsPanel from "./components/ActionsPanel";
import MissionTelemetryPanel from "./components/MissionTelemetryPanel";

function App() {
  const [telemetry, setTelemetry] = useState(null);
  const [hasVessel, setHasVessel] = useState(false);
  const [connectionState, setConnectionState] = useState("connecting");
  const [activeActionId, setActiveActionId] = useState(null);
  const [missionActive, setMissionActive] = useState(false);
  const [visualResetKey, setVisualResetKey] = useState(0);
  const hasVesselRef = useRef(hasVessel);
  const activeActionIdRef = useRef(activeActionId);
  const activeActionStartedAtRef = useRef(0);
  const visualResetSequenceRef = useRef(null);
  const isPollingRef = useRef(false);

  const isActionRunning = activeActionId !== null || missionActive;

  useEffect(() => {
    hasVesselRef.current = hasVessel;
  }, [hasVessel]);

  useEffect(() => {
    activeActionIdRef.current = activeActionId;
  }, [activeActionId]);

  const pollTelemetry = useCallback(async (options = {}) => {
    try {
      const data = await getTelemetry(options);
      const hasActiveVessel = Boolean(data.has_vessel);

      setTelemetry(hasActiveVessel ? (data.telemetry ?? null) : null);
      setHasVessel(hasActiveVessel);
      setConnectionState(hasActiveVessel ? "live" : "idle");

      if (!hasActiveVessel) {
        setActiveActionId(null);
        setMissionActive(false);
      }
    } catch (error) {
      if (error.name === "AbortError") {
        return;
      }

      setTelemetry(null);
      setHasVessel(false);
      setConnectionState("offline");
    }
  }, []);

  const pollMissionStatus = useCallback(async () => {
    try {
      const data = await getMissionStatus();
      const actionHasSettled = Date.now() - activeActionStartedAtRef.current > 750;
      const resetSequence = data.mission?.visual_reset_sequence;
      const isMissionActive = Boolean(data.mission?.active);
      const missionActionId = data.mission?.action ?? null;

      setMissionActive(isMissionActive);

      if (isMissionActive && missionActionId) {
        setActiveActionId(missionActionId);
      }

      if (
        Number.isFinite(resetSequence) &&
        visualResetSequenceRef.current !== resetSequence
      ) {
        visualResetSequenceRef.current = resetSequence;
        setVisualResetKey(resetSequence);
      }

      if (activeActionIdRef.current && actionHasSettled && !isMissionActive) {
        setActiveActionId(null);
      }
    } catch {
      setActiveActionId(null);
      setMissionActive(false);
    }
  }, []);

  async function handleRunAction(actionId) {
    setActiveActionId(actionId);
    activeActionStartedAtRef.current = Date.now();

    try {
      await runKspAction(actionId);
      await pollTelemetry();
    } catch {
      await pollTelemetry();
    } finally {
      await pollMissionStatus();
    }

    const actionHasSettled = Date.now() - activeActionStartedAtRef.current > 750;

    if (actionHasSettled && !activeActionIdRef.current) {
      setActiveActionId(null);
    }
  }

  async function handleAbortAction() {
    try {
      await abortKspAction();
    } finally {
      setActiveActionId(null);
      setMissionActive(false);
      await pollMissionStatus();
      await pollTelemetry();
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
          await pollMissionStatus();
          await pollTelemetry();
        } finally {
          isPollingRef.current = false;
        }
      }

      const intervalMs = hasVesselRef.current ? 100 : 500;
      timeoutId = window.setTimeout(runPoll, intervalMs);
    }

    runPoll();

    return () => {
      isMounted = false;

      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [pollMissionStatus, pollTelemetry]);

  return (
    <main className="app">
      <header className="app-header">
        <div>
          <p className="eyebrow">KSP Control Panel</p>
          <h1>Mission Dashboard</h1>
        </div>

      </header>

      <section className="dashboard-grid">
        <ActionsPanel
          actions={ACTIONS}
          activeActionId={activeActionId}
          connectionState={connectionState}
          isLoading={isActionRunning}
          missionActive={missionActive}
          onAbortAction={handleAbortAction}
          onRunAction={handleRunAction}
        />

        <MissionTelemetryPanel
          telemetry={telemetry}
          hasVessel={hasVessel}
          visualResetKey={visualResetKey}
        />
      </section>
    </main>
  );
}

export default App;
