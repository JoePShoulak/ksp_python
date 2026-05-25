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
const VESSEL_LOST_FAILURE_LIMIT = 20;
const POLL_TIMEOUT_MS = 2500;
const LIVE_POLL_INTERVAL_MS = 750;
const IDLE_POLL_INTERVAL_MS = 750;
const MISSION_STATUS_INTERVAL_MS = 1500;
const BACKEND_HEALTH_INTERVAL_MS = 5000;
const API_RECENT_SUCCESS_MS = 15000;
const MISSION_PHASE_ACTIONS = {
  Launch: "launch_rocket",
  Land: "land_rocket",
  Wait: "wait_one_hour",
  lko_tourism: "lko_tourism",
};

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
  const lastApiSuccessAtRef = useRef(0);
  const vesselLostCountRef = useRef(0);
  const [pendingActionId, setPendingActionId] = useState(null);

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

  function markApiSuccess() {
    lastApiSuccessAtRef.current = Date.now();
    healthFailureCountRef.current = 0;
  }

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
      const resetSequence = data.visual_reset_sequence;

      markApiSuccess();

      if (
        Number.isFinite(resetSequence) &&
        visualResetSequenceRef.current !== resetSequence
      ) {
        visualResetSequenceRef.current = resetSequence;
        setVisualResetKey(resetSequence);
      }

      if (hasActiveVessel) {
        vesselLostCountRef.current = 0;
        setTelemetry(data.telemetry ?? null);
        setHasVessel(true);
        setConnectionState("live");
        return;
      }

      vesselLostCountRef.current += 1;

      if (!hasVesselRef.current || vesselLostCountRef.current >= VESSEL_LOST_FAILURE_LIMIT) {
        setTelemetry(null);
        setHasVessel(false);

        setConnectionState("idle");
        setActiveActionId(null);
        setMissionActive(false);
        setPendingActionId(null);
        setActionError(null);
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
      markApiSuccess();
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

      if (activeActionIdRef.current || missionActiveRef.current) {
        setBackendHealth(currentHealth => ({
          ...currentHealth,
          state: "busy",
          checkedAt: Date.now(),
          error: "Mission command in progress",
        }));
        return;
      }

      const hasRecentApiSuccess =
        Date.now() - lastApiSuccessAtRef.current < API_RECENT_SUCCESS_MS;

      if (
        healthFailureCountRef.current >= BACKEND_OFFLINE_FAILURE_LIMIT &&
        !hasRecentApiSuccess &&
        !telemetryRef.current
      ) {
        setBackendHealth({
          state: "offline",
          checkedAt: Date.now(),
          data: null,
          error: "No response from backend",
        });

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
      const missionActionId = getMissionActionId(data.mission);
      const missionError = data.mission?.last_error ?? null;
      const vesselLostGracefully = isGracefulVesselLostError(missionError);
      const hasKnownVessel = hasVesselRef.current || Boolean(telemetryRef.current);
      const shouldShowMissionAction =
        !vesselLostGracefully &&
        hasKnownVessel &&
        (isMissionActive || Boolean(missionActionId));
      const isMissionOrActionActive = shouldShowMissionAction;

      markApiSuccess();
      setBackendHealth(currentHealth => ({
        ...currentHealth,
        state: "online",
        checkedAt: currentHealth.checkedAt ?? Date.now(),
        error: null,
      }));
      setMissionActive(vesselLostGracefully ? false : isMissionOrActionActive);

      if (vesselLostGracefully) {
        setActionError(null);
        setActiveActionId(null);
        setPendingActionId(null);
      } else if (missionError) {
        setActionError(missionError);
      }

      if (shouldShowMissionAction && missionActionId) {
        setActiveActionId(missionActionId);
      }

      if (
        Number.isFinite(resetSequence) &&
        visualResetSequenceRef.current !== resetSequence
      ) {
        visualResetSequenceRef.current = resetSequence;
        setVisualResetKey(resetSequence);
      }

      if (activeActionIdRef.current && actionHasSettled && !isMissionOrActionActive) {
        setActiveActionId(null);
      }
    } catch {
      if (!activeActionIdRef.current) {
        setMissionActive(false);
      }
    }
  }, []);

  async function handleRunAction(actionId) {
    const previousActionId = activeActionIdRef.current;

    if (
      !hasVesselRef.current ||
      pendingActionId ||
      activeActionIdRef.current ||
      missionActiveRef.current
    ) {
      return;
    }

    setPendingActionId(actionId);
    setActionError(null);
    activeActionStartedAtRef.current = Date.now();
    await new Promise(resolve => window.requestAnimationFrame(resolve));

    try {
      await runKspAction(actionId);
      setActiveActionId(actionId);
      setMissionActive(true);
    } catch (error) {
      setActionError(error.message || "Mission request failed");
      setActiveActionId(previousActionId);
      setPendingActionId(null);
      return;
    }

    try {
      await pollTelemetry();
    } catch {
      // The mission was accepted; telemetry will catch up on the normal poll loop.
    }

    try {
      await pollMissionStatus();
    } catch {
      // The mission was accepted; mission status will catch up on the normal poll loop.
    }

    const actionHasSettled = Date.now() - activeActionStartedAtRef.current > 750;

    if (actionHasSettled && !activeActionIdRef.current) {
      setActiveActionId(null);
    }

    setPendingActionId(null);
  }

  async function handleAbortAction() {
    setPendingActionId(null);
    setActiveActionId(null);
    setMissionActive(false);
    setActionError(null);

    try {
      await abortKspAction();
    } catch (error) {
      setActionError(error.message || "Abort request failed");
    }

    try {
      await pollMissionStatus();
    } catch {
      // The abort request was sent; the normal poll loop will retry status.
    }

    try {
      await pollTelemetry();
    } catch {
      // The abort request was sent; the normal poll loop will retry telemetry.
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
          pendingActionId={pendingActionId}
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

function getMissionActionId(mission) {
  if (!mission) {
    return null;
  }

  if (mission.action) {
    return mission.action;
  }

  return MISSION_PHASE_ACTIONS[mission.phase] ?? null;
}

function isGracefulVesselLostError(message) {
  return String(message || "").includes("active vessel is no longer available");
}
