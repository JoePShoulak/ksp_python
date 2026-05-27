import "./styles/app-shell.css";
import "./styles/panels.css";
import "./styles/telemetry.css";
import "./styles/responsive.css";

import { useState } from "react";

import { ACTIONS } from "./data/actions";
import ActionsPanel from "./components/ActionsPanel";
import FullscreenButton from "./components/FullscreenButton";
import MissionTelemetryPanel from "./components/MissionTelemetryPanel";
import Panel from "./components/Panel";
import VisualizationSubpanel from "./components/visualizations/VisualizationSubpanel";
import AscentCartesian from "./components/visualizations/AscentCartesian";
import AscentPolar from "./components/visualizations/AscentPolar";
import CameraStream from "./components/visualizations/CameraStream";
import KerbinSystemMap from "./components/visualizations/KerbinSystemMap";
import NumericalTelemetry from "./components/visualizations/NumericalTelemetry";
import VesselStatus from "./components/visualizations/VesselStatus";
import { useKspPolling } from "./hooks/useKspPolling";
import { useViewportReport } from "./hooks/useViewportReport";
import { buildPopoutId } from "./utils/popoutIds";

const MISSION_OPTIONS_STORAGE_KEY = "kspMissionOptions";
const DEFAULT_MISSION_OPTIONS = {
  revertOnFailure: false,
  retryOnRevert: false,
};

function readStoredMissionOptions() {
  try {
    const storedOptions = JSON.parse(
      window.localStorage.getItem(MISSION_OPTIONS_STORAGE_KEY),
    );

    return {
      revertOnFailure: Boolean(storedOptions?.revertOnFailure),
      retryOnRevert: Boolean(
        storedOptions?.retryOnRevert && storedOptions?.revertOnFailure,
      ),
    };
  } catch {
    return DEFAULT_MISSION_OPTIONS;
  }
}

function App() {
  useViewportReport();
  const popoutId = new URLSearchParams(window.location.search).get("popout");
  const [missionOptions, setMissionOptions] = useState(readStoredMissionOptions);

  const {
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
  } = useKspPolling();

  function updateMissionOption(option, value) {
    setMissionOptions(currentOptions => {
      const nextOptions = {
        ...currentOptions,
        [option]: value,
      };

      if (option === "revertOnFailure" && !value) {
        nextOptions.retryOnRevert = false;
      }

      window.localStorage.setItem(
        MISSION_OPTIONS_STORAGE_KEY,
        JSON.stringify(nextOptions),
      );

      return nextOptions;
    });
  }

  if (popoutId) {
    return (
      <PopoutDashboard
        popoutId={popoutId}
        telemetry={telemetry}
        hasVessel={hasVessel}
        connectionState={connectionState}
        activeActionId={activeActionId}
        missionActive={missionActive}
        actionError={actionError}
        visualResetKey={visualResetKey}
        backendHealth={backendHealth}
        pendingActionId={pendingActionId}
        missionOptions={missionOptions}
        onReleaseAction={releaseAction}
        onRevertToLaunch={revertToLaunch}
        onMissionOptionChange={updateMissionOption}
        onRunAction={runAction}
      />
    );
  }

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
          missionOptions={missionOptions}
          pendingActionId={pendingActionId}
          actionError={actionError}
          missionActive={missionActive}
          onReleaseAction={releaseAction}
          onRevertToLaunch={revertToLaunch}
          onMissionOptionChange={updateMissionOption}
          onRunAction={runAction}
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

function PopoutDashboard({
  popoutId,
  telemetry,
  hasVessel,
  connectionState,
  activeActionId,
  missionActive,
  actionError,
  visualResetKey,
  backendHealth,
  pendingActionId,
  missionOptions,
  onReleaseAction,
  onRevertToLaunch,
  onMissionOptionChange,
  onRunAction,
}) {
  const hasCameras = Boolean(telemetry?.cameras?.available);
  const missionLabel = missionActive ? telemetry?.status : null;
  const vesselStatusTitle = missionLabel
    ? `Vessel Status - ${missionLabel}`
    : "Vessel Status";

  let content;

  if (popoutId === buildPopoutId("Missions")) {
    content = (
      <ActionsPanel
        actions={ACTIONS}
        activeActionId={activeActionId}
        connectionState={connectionState}
        backendHealth={backendHealth}
        missionOptions={missionOptions}
        pendingActionId={pendingActionId}
        actionError={actionError}
        missionActive={missionActive}
        onReleaseAction={onReleaseAction}
        onRevertToLaunch={onRevertToLaunch}
        onMissionOptionChange={onMissionOptionChange}
        onRunAction={onRunAction}
        allowPopout={false}
      />
    );
  } else if (!hasVessel) {
    content = (
      <Panel title="Telemetry" popout={false}>
        <div className="idle-panel">
          <div className="idle-orb" />
          <div>
            <h3>No active vessel</h3>
            <p>Waiting for KSP/kRPC and an active vessel.</p>
          </div>
        </div>
      </Panel>
    );
  } else if (popoutId === buildPopoutId("Vessel Status")) {
    content = (
      <VisualizationSubpanel
        title={vesselStatusTitle}
        variant="primary"
        popout={false}>
        <VesselStatus telemetry={telemetry} />
      </VisualizationSubpanel>
    );
  } else if (popoutId === buildPopoutId("Numerical Telemetry")) {
    content = (
      <VisualizationSubpanel
        title="Numerical Telemetry"
        variant="secondary"
        popout={false}>
        <NumericalTelemetry telemetry={telemetry} />
      </VisualizationSubpanel>
    );
  } else if (popoutId === buildPopoutId("Camera Feed") && hasCameras) {
    content = (
      <VisualizationSubpanel title="Camera Feed" variant="camera" popout={false}>
        <CameraStream cameras={telemetry.cameras} />
      </VisualizationSubpanel>
    );
  } else if (popoutId === buildPopoutId("Ascent Cartesian")) {
    content = (
      <VisualizationSubpanel title="Ascent - Cartesian" popout={false}>
        <AscentCartesian
          key={`cartesian-popout-${visualResetKey}`}
          telemetry={telemetry}
        />
      </VisualizationSubpanel>
    );
  } else if (popoutId === buildPopoutId("Ascent Polar")) {
    content = (
      <VisualizationSubpanel title="Ascent - Polar" popout={false}>
        <AscentPolar
          key={`polar-popout-${visualResetKey}`}
          telemetry={telemetry}
        />
      </VisualizationSubpanel>
    );
  } else if (popoutId === buildPopoutId("Kerbin System")) {
    content = (
      <VisualizationSubpanel title="Kerbin System" popout={false}>
        <KerbinSystemMap
          key={`kerbin-popout-${visualResetKey}`}
          telemetry={telemetry}
        />
      </VisualizationSubpanel>
    );
  } else {
    content = (
      <Panel title="Card unavailable" popout={false}>
        <div className="idle-panel">
          <div>
            <h3>Waiting for card data</h3>
            <p>This card will render when its telemetry is available.</p>
          </div>
        </div>
      </Panel>
    );
  }

  return (
    <main className="app popout-app">
      {content}
    </main>
  );
}

export default App;
