import "./styles/app-shell.css";
import "./styles/panels.css";
import "./styles/telemetry.css";
import "./styles/responsive.css";

import { ACTIONS } from "./data/actions";
import ActionsPanel from "./components/ActionsPanel";
import FullscreenButton from "./components/FullscreenButton";
import MissionTelemetryPanel from "./components/MissionTelemetryPanel";
import { useKspPolling } from "./hooks/useKspPolling";
import { useViewportReport } from "./hooks/useViewportReport";

function App() {
  useViewportReport();

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
    abortAction,
    runAction,
  } = useKspPolling();

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
          onAbortAction={abortAction}
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

export default App;
