import Panel from "./Panel";
import VisualizationSubpanel from "./visualizations/VisualizationSubpanel";
import VesselStatus from "./visualizations/VesselStatus";
import NumericalTelemetry from "./visualizations/NumericalTelemetry";
import AscentCartesian from "./visualizations/AscentCartesian";
import AscentPolar from "./visualizations/AscentPolar";
import CameraStream from "./visualizations/CameraStream";
import KerbinSystemMap from "./visualizations/KerbinSystemMap";

function IdleTelemetryPanel() {
  return (
    <Panel title="Telemetry">
      <div className="idle-panel">
        <div className="idle-orb" />

        <div>
          <h3>No active vessel</h3>
          <p>
            Waiting for KSP/kRPC and an active vessel. This dashboard will
            connect automatically when telemetry becomes available.
          </p>
        </div>
      </div>
    </Panel>
  );
}

function MissionTelemetryPanel({
  telemetry,
  hasVessel,
  cameraPaused,
  missionActive,
  visualResetKey,
}) {
  if (!hasVessel) {
    return <IdleTelemetryPanel />;
  }

  const hasCameras = Boolean(telemetry?.cameras?.available);

  return (
    <Panel title="Telemetry">
      <div className="visualization-grid">
        <VisualizationSubpanel title="Vessel Status" variant="primary">
          <VesselStatus telemetry={telemetry} />
        </VisualizationSubpanel>

        <VisualizationSubpanel title="Numerical Telemetry" variant="secondary">
          <NumericalTelemetry telemetry={telemetry} missionActive={missionActive} />
        </VisualizationSubpanel>

        {hasCameras && (
          <VisualizationSubpanel title="Camera Feed" variant="camera">
            <CameraStream cameras={telemetry.cameras} paused={cameraPaused} />
          </VisualizationSubpanel>
        )}

        <VisualizationSubpanel title="Ascent - Cartesian">
          <AscentCartesian
            key={`cartesian-${visualResetKey}`}
            telemetry={telemetry}
          />
        </VisualizationSubpanel>

        <VisualizationSubpanel title="Ascent - Polar">
          <AscentPolar key={`polar-${visualResetKey}`} telemetry={telemetry} />
        </VisualizationSubpanel>

        <VisualizationSubpanel title="Kerbin System">
          <KerbinSystemMap
            key={`kerbin-${visualResetKey}`}
            telemetry={telemetry}
          />
        </VisualizationSubpanel>
      </div>
    </Panel>
  );
}

export default MissionTelemetryPanel;
