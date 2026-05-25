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
  getBackendHealth,
  reportViewport,
  runKspAction,
} from "./api/kspApi";

import ActionsPanel from "./components/ActionsPanel";
import FullscreenButton from "./components/FullscreenButton";
import MissionTelemetryPanel from "./components/MissionTelemetryPanel";

const BACKEND_OFFLINE_FAILURE_LIMIT = 3;
const VESSEL_LOST_FAILURE_LIMIT = 10;
const POLL_TIMEOUT_MS = 2500;
const LIVE_POLL_INTERVAL_MS = 750;
const IDLE_POLL_INTERVAL_MS = 750;
const MISSION_STATUS_INTERVAL_MS = 1500;
const BACKEND_HEALTH_INTERVAL_MS = 5000;

function App() {
  const [telemetry, setTelemetry] = useState(null);
  const [hasVessel, setHasVessel] = useState(false);
  const [connectionState, setConnectionState] = useState("connecting");
  const [activeActionId, setActiveActionId] = useState(null);
  const [missionActive, setMissionActive] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [visualResetKey, setVisualResetKey] = useState(0);
  const [backendHealth, setBackendHealth] = useState({
    state: "checking",
    checkedAt: null,
    data: null,
    error: null,
  });
  const hasVesselRef = useRef(hasVessel);
  const telemetryRef = useRef(telemetry);
  const connectionStateRef = useRef(connectionState);
  const activeActionIdRef = useRef(activeActionId);
  const missionActiveRef = useRef(missionActive);
  const activeActionStartedAtRef = useRef(0);
  const lastMissionStatusPollRef = useRef(0);
  const lastBackendHealthPollRef = useRef(0);
  const visualResetSequenceRef = useRef(null);
  const isPollingRef = useRef(false);
  const healthFailureCountRef = useRef(0);
  const vesselLostCountRef = useRef(0);

  const isActionRunning = activeActionId !== null || missionActive;

  useEffect(() => {
    hasVesselRef.current = hasVessel;
  }, [hasVessel]);

  useEffect(() => {
    telemetryRef.current = telemetry;
  }, [telemetry]);

  useEffect(() => {
    connectionStateRef.current = connectionState;
  }, [connectionState]);

  useEffect(() => {
    activeActionIdRef.current = activeActionId;
  }, [activeActionId]);

  useEffect(() => {
    missionActiveRef.current = missionActive;
  }, [missionActive]);

  useEffect(() => {
    let timeoutId = null;

    function readViewport() {
      const width = window.visualViewport?.width ?? window.innerWidth;
      const height = window.visualViewport?.height ?? window.innerHeight;
      const report = {
        client_id: window.localStorage.getItem("kspViewportClientId"),
        viewport_width: Math.round(width),
        viewport_height: Math.round(height),
        layout_width: window.innerWidth,
        layout_height: window.innerHeight,
        screen_width: window.screen?.width,
        screen_height: window.screen?.height,
        available_width: window.screen?.availWidth,
        available_height: window.screen?.availHeight,
        device_pixel_ratio: window.devicePixelRatio,
        orientation:
          window.screen?.orientation?.type ??
          (window.innerWidth >= window.innerHeight ? "landscape" : "portrait"),
        user_agent: window.navigator.userAgent,
      };

      if (!report.client_id) {
        report.client_id = `viewport-${Date.now()}-${Math.random()
          .toString(36)
          .slice(2)}`;
        window.localStorage.setItem("kspViewportClientId", report.client_id);
      }

      return report;
    }

    function sendViewport() {
      const report = readViewport();

      console.info(
        "[KSP viewport]",
        `${report.viewport_width}x${report.viewport_height}`,
        `layout=${report.layout_width}x${report.layout_height}`,
        `screen=${report.screen_width}x${report.screen_height}`,
        `dpr=${report.device_pixel_ratio}`,
        report.orientation,
      );

      reportViewport(report).catch(() => {});
    }

    function scheduleViewportReport() {
      window.clearTimeout(timeoutId);
      timeoutId = window.setTimeout(sendViewport, 150);
    }

    sendViewport();
    window.addEventListener("resize", scheduleViewportReport);
    window.visualViewport?.addEventListener("resize", scheduleViewportReport);
    window.screen?.orientation?.addEventListener?.("change", scheduleViewportReport);

    return () => {
      window.clearTimeout(timeoutId);
      window.removeEventListener("resize", scheduleViewportReport);
      window.visualViewport?.removeEventListener("resize", scheduleViewportReport);
      window.screen?.orientation?.removeEventListener?.(
        "change",
        scheduleViewportReport,
      );
    };
  }, []);

  const pollTelemetry = useCallback(async (options = {}) => {
    try {
      const data = await getTelemetry(options);
      const hasActiveVessel = Boolean(data.has_vessel);

      if (hasActiveVessel) {
        vesselLostCountRef.current = 0;
        setTelemetry(data.telemetry ?? null);
        setHasVessel(true);
        setConnectionState("live");
        return;
      }

      vesselLostCountRef.current += 1;

      if (!hasVesselRef.current || vesselLostCountRef.current >= VESSEL_LOST_FAILURE_LIMIT) {
        if (!telemetryRef.current) {
          setTelemetry(null);
          setHasVessel(false);
        }

        setConnectionState("idle");
        setActiveActionId(null);
        setMissionActive(false);
      }
    } catch (error) {
      if (error.name === "AbortError") {
        return;
      }
    }
  }, []);

  const pollBackendHealth = useCallback(async () => {
    try {
      const data = await getBackendHealth({ timeoutMs: POLL_TIMEOUT_MS });
      healthFailureCountRef.current = 0;
      setBackendHealth({
        state: "online",
        checkedAt: Date.now(),
        data,
        error: null,
      });

      setConnectionState(currentState =>
        currentState === "connecting" || currentState === "offline"
          ? "idle"
          : currentState,
      );
    } catch {
      healthFailureCountRef.current += 1;

      if (healthFailureCountRef.current >= BACKEND_OFFLINE_FAILURE_LIMIT) {
        setBackendHealth({
          state: "offline",
          checkedAt: Date.now(),
          data: null,
          error: "No response from backend",
        });

        if (!telemetryRef.current) {
          setTelemetry(null);
          setHasVessel(false);
        }

        setConnectionState("offline");
      } else {
        setBackendHealth(currentHealth => ({
          ...currentHealth,
          state: currentHealth.state === "online" ? "online" : "checking",
          checkedAt: Date.now(),
          error: "Health check missed",
        }));
      }
    }
  }, []);

  const pollMissionStatus = useCallback(async (options = {}) => {
    try {
      const data = await getMissionStatus(options);
      const actionHasSettled = Date.now() - activeActionStartedAtRef.current > 750;
      const resetSequence = data.mission?.visual_reset_sequence;
      const isMissionActive = Boolean(data.mission?.active);
      const missionActionId = data.mission?.action ?? null;
      const missionError = data.mission?.last_error ?? null;

      setMissionActive(isMissionActive);

      if (missionError) {
        setActionError(missionError);
      }

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
    setActionError(null);
    activeActionStartedAtRef.current = Date.now();
    await new Promise(resolve => window.requestAnimationFrame(resolve));

    try {
      await runKspAction(actionId);
      await pollTelemetry();
    } catch (error) {
      setActionError(error.message || "Mission request failed");
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
      setActionError(null);
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
          const now = Date.now();
          const shouldPollMissionStatus =
            activeActionIdRef.current ||
            missionActiveRef.current ||
            now - lastMissionStatusPollRef.current >= MISSION_STATUS_INTERVAL_MS;
          const shouldPollBackendHealth =
            connectionStateRef.current !== "live" ||
            now - lastBackendHealthPollRef.current >= BACKEND_HEALTH_INTERVAL_MS;
          const checks = [pollTelemetry({ timeoutMs: POLL_TIMEOUT_MS })];

          if (shouldPollMissionStatus) {
            lastMissionStatusPollRef.current = now;
            checks.push(pollMissionStatus({ timeoutMs: POLL_TIMEOUT_MS }));
          }

          if (shouldPollBackendHealth) {
            lastBackendHealthPollRef.current = now;
            checks.push(pollBackendHealth());
          }

          await Promise.allSettled(checks);
        } finally {
          isPollingRef.current = false;
        }
      }

      const intervalMs = hasVesselRef.current
        ? LIVE_POLL_INTERVAL_MS
        : IDLE_POLL_INTERVAL_MS;
      timeoutId = window.setTimeout(runPoll, intervalMs);
    }

    runPoll();

    return () => {
      isMounted = false;

      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [pollBackendHealth, pollMissionStatus, pollTelemetry]);

  return (
    <main className="app">
      <header className="app-header">
        <div>
          <p className="eyebrow">KSP Control Panel</p>
          <h1>Mission Dashboard</h1>
        </div>

        <FullscreenButton />
      </header>

      <section className="dashboard-grid">
        <ActionsPanel
          actions={ACTIONS}
          activeActionId={activeActionId}
          connectionState={connectionState}
          backendHealth={backendHealth}
          isLoading={isActionRunning}
          actionError={actionError}
          missionActive={missionActive}
          onAbortAction={handleAbortAction}
          onRunAction={handleRunAction}
        />

        <MissionTelemetryPanel
          telemetry={telemetry}
          hasVessel={hasVessel}
          missionActive={missionActive}
          visualResetKey={visualResetKey}
        />
      </section>
    </main>
  );
}

export default App;
