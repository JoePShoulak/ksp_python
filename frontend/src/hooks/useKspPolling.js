import { useCallback, useEffect, useRef, useState } from "react";

import {
  releaseKspAction,
  getBackendHealth,
  getMissionStatus,
  getTelemetry,
  revertKspToLaunch,
  runKspAction,
} from "../api/kspApi";

const BACKEND_OFFLINE_FAILURE_LIMIT = 3;
const VESSEL_RECONNECT_FAILURE_LIMIT = 20;
const POLL_TIMEOUT_MS = 2500;
const LIVE_POLL_INTERVAL_MS = 1000;
const IDLE_POLL_INTERVAL_MS = 3000;
const HIDDEN_POLL_INTERVAL_MS = 5000;
const MISSION_STATUS_INTERVAL_MS = 1500;
const IDLE_MISSION_STATUS_INTERVAL_MS = 5000;
const BACKEND_HEALTH_INTERVAL_MS = 5000;
const API_RECENT_SUCCESS_MS = 15000;
const ACTION_SETTLE_MS = 750;
const MISSION_PHASE_ACTIONS = {
  Launch: "launch_rocket",
  Land: "land_rocket",
  "Mun Flyby": "flyby_mun",
  "Periapsis Circularize": "circularize_at_periapsis",
  Wait: "wait_one_hour",
  lko_tourism: "lko_tourism",
};

const INITIAL_BACKEND_HEALTH = {
  state: "checking",
  checkedAt: null,
  data: null,
  error: null,
};

export function useKspPolling() {
  const [telemetry, setTelemetry] = useState(null);
  const [hasVessel, setHasVessel] = useState(false);
  const [connectionState, setConnectionState] = useState("connecting");
  const [activeActionId, setActiveActionId] = useState(null);
  const [missionActive, setMissionActive] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [visualResetKey, setVisualResetKey] = useState(0);
  const [backendHealth, setBackendHealth] = useState(INITIAL_BACKEND_HEALTH);
  const [pendingActionId, setPendingActionId] = useState(null);

  const hasVesselRef = useLatestRef(hasVessel);
  const telemetryRef = useLatestRef(telemetry);
  const activeActionIdRef = useLatestRef(activeActionId);
  const missionActiveRef = useLatestRef(missionActive);
  const activeActionStartedAtRef = useRef(0);
  const lastMissionStatusPollRef = useRef(0);
  const lastBackendHealthPollRef = useRef(0);
  const visualResetSequenceRef = useRef(null);
  const isPollingRef = useRef(false);
  const healthFailureCountRef = useRef(0);
  const lastApiSuccessAtRef = useRef(0);
  const vesselReconnectFailureCountRef = useRef(0);

  const markApiSuccess = useCallback(() => {
    lastApiSuccessAtRef.current = Date.now();
    healthFailureCountRef.current = 0;
  }, []);

  const syncVisualResetSequence = useCallback(resetSequence => {
    if (
      Number.isFinite(resetSequence) &&
      visualResetSequenceRef.current !== resetSequence
    ) {
      visualResetSequenceRef.current = resetSequence;
      setVisualResetKey(resetSequence);
    }
  }, []);

  const clearVesselState = useCallback(() => {
    setTelemetry(null);
    setHasVessel(false);
    setConnectionState("idle");
    setActiveActionId(null);
    setMissionActive(false);
    setPendingActionId(null);
    setActionError(null);
  }, []);

  const pollTelemetry = useCallback(async (options = {}) => {
    try {
      const data = await getTelemetry(options);
      const hasActiveVessel = Boolean(data.has_vessel);

      markApiSuccess();
      syncVisualResetSequence(data.visual_reset_sequence);

      if (hasActiveVessel) {
        vesselReconnectFailureCountRef.current = 0;
        setTelemetry(data.telemetry ?? null);
        setHasVessel(true);
        setConnectionState("live");
        return;
      }

      vesselReconnectFailureCountRef.current += 1;

      if (
        !hasVesselRef.current ||
        vesselReconnectFailureCountRef.current >= VESSEL_RECONNECT_FAILURE_LIMIT
      ) {
        clearVesselState();
      }
    } catch (error) {
      if (error.name === "AbortError") {
        return;
      }
    }
  }, [clearVesselState, hasVesselRef, markApiSuccess, syncVisualResetSequence]);

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
  }, [activeActionIdRef, markApiSuccess, missionActiveRef, telemetryRef]);

  const pollMissionStatus = useCallback(async (options = {}) => {
    try {
      const data = await getMissionStatus(options);
      const actionHasSettled =
        Date.now() - activeActionStartedAtRef.current > ACTION_SETTLE_MS;
      const mission = data.mission;
      const missionActionId = getMissionActionId(mission);
      const missionError = mission?.last_error ?? null;
      const vesselLostGracefully = isGracefulVesselLostError(missionError);
      const hasKnownVessel = hasVesselRef.current || Boolean(telemetryRef.current);
      const shouldShowMissionAction =
        !vesselLostGracefully &&
        hasKnownVessel &&
        (Boolean(mission?.active) || Boolean(missionActionId));

      markApiSuccess();
      setBackendHealth(currentHealth => ({
        ...currentHealth,
        state: "online",
        checkedAt: currentHealth.checkedAt ?? Date.now(),
        error: null,
      }));
      setMissionActive(vesselLostGracefully ? false : shouldShowMissionAction);

      if (vesselLostGracefully) {
        setActionError(null);
        setActiveActionId(null);
        setPendingActionId(null);
      } else if (isIgnorableTelemetryInitError(missionError)) {
        setActionError(null);
      } else if (missionError) {
        setActionError(missionError);
      }

      if (shouldShowMissionAction && missionActionId) {
        setActiveActionId(missionActionId);
      }

      syncVisualResetSequence(mission?.visual_reset_sequence);

      if (activeActionIdRef.current && actionHasSettled && !shouldShowMissionAction) {
        setActiveActionId(null);
      }
    } catch {
      if (!activeActionIdRef.current) {
        setMissionActive(false);
      }
    }
  }, [
    activeActionIdRef,
    hasVesselRef,
    markApiSuccess,
    syncVisualResetSequence,
    telemetryRef,
  ]);

  const runAction = useCallback(async (actionId, options = {}) => {
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
      await runKspAction(actionId, normalizeMissionOptions(actionId, options));
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

    const actionHasSettled =
      Date.now() - activeActionStartedAtRef.current > ACTION_SETTLE_MS;

    if (actionHasSettled && !activeActionIdRef.current) {
      setActiveActionId(null);
    }

    setPendingActionId(null);
  }, [
    activeActionIdRef,
    hasVesselRef,
    missionActiveRef,
    pendingActionId,
    pollMissionStatus,
    pollTelemetry,
  ]);

  const releaseAction = useCallback(async () => {
    setPendingActionId(null);
    setActiveActionId(null);
    setMissionActive(false);
    setActionError(null);

    try {
      await releaseKspAction();
    } catch (error) {
      setActionError(error.message || "Release request failed");
    }

    try {
      await pollMissionStatus();
    } catch {
      // The release request was sent; the normal poll loop will retry status.
    }

    try {
      await pollTelemetry();
    } catch {
      // The release request was sent; the normal poll loop will retry telemetry.
    }
  }, [pollMissionStatus, pollTelemetry]);

  const revertToLaunch = useCallback(async () => {
    setPendingActionId(null);
    setActiveActionId(null);
    setMissionActive(false);
    setActionError(null);

    try {
      await revertKspToLaunch();
    } catch (error) {
      setActionError(error.message || "Revert request failed");
    }

    try {
      await pollMissionStatus();
    } catch {
      // The revert request was sent; the normal poll loop will retry status.
    }

    try {
      await pollTelemetry();
    } catch {
      // The revert request was sent; the normal poll loop will retry telemetry.
    }
  }, [pollMissionStatus, pollTelemetry]);

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
          const missionBusy =
            activeActionIdRef.current || missionActiveRef.current;
          const missionStatusIntervalMs = hasVesselRef.current
            ? MISSION_STATUS_INTERVAL_MS
            : IDLE_MISSION_STATUS_INTERVAL_MS;
          const shouldPollMissionStatus =
            missionBusy ||
            now - lastMissionStatusPollRef.current >= missionStatusIntervalMs;
          const shouldPollBackendHealth =
            lastBackendHealthPollRef.current === 0 ||
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

      const intervalMs = document.hidden
        ? HIDDEN_POLL_INTERVAL_MS
        : hasVesselRef.current
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
  }, [
    activeActionIdRef,
    hasVesselRef,
    missionActiveRef,
    pollBackendHealth,
    pollMissionStatus,
    pollTelemetry,
  ]);

  return {
    telemetry,
    hasVessel,
    connectionState,
    activeActionId,
    missionActive,
    actionError,
    visualResetKey,
    backendHealth,
    pendingActionId,
    releaseAction,
    revertToLaunch,
    runAction,
  };
}

function useLatestRef(value) {
  const ref = useRef(value);

  useEffect(() => {
    ref.current = value;
  }, [value]);

  return ref;
}

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

function isIgnorableTelemetryInitError(message) {
  return String(message || "").includes("Telemetry has not been initialized");
}

function normalizeMissionOptions(actionId, options) {
  if (!["launch_rocket", "lko_tourism"].includes(actionId)) {
    return {};
  }

  return {
    revert_on_failure: Boolean(options.revertOnFailure),
    retry_on_revert: Boolean(options.retryOnRevert && options.revertOnFailure),
  };
}
