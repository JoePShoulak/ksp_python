import Panel from "./Panel";
import VisualizationSubpanel from "./visualizations/VisualizationSubpanel";
import VesselStatus from "./visualizations/VesselStatus";
import NumericalTelemetry from "./visualizations/NumericalTelemetry";
import AscentCartesian from "./visualizations/AscentCartesian";
import AscentPolar from "./visualizations/AscentPolar";
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

function VisDatPanel({ telemetry, hasVessel }) {
  if (!hasVessel) {
    return <IdleTelemetryPanel />;
  }

  return (
    <Panel title="Telemetry">
      <div className="visualization-grid">
        <VisualizationSubpanel title="Vessel Status" className="wide-subpanel">
          <VesselStatus telemetry={telemetry} />
        </VisualizationSubpanel>

        <VisualizationSubpanel
          title="Numerical Telemetry"
          className="wide-subpanel">
          <NumericalTelemetry telemetry={telemetry} />
        </VisualizationSubpanel>

        <VisualizationSubpanel title="Kerbin System">
          <KerbinSystemMap telemetry={telemetry} />
        </VisualizationSubpanel>

        <VisualizationSubpanel title="Ascent - Polar">
          <AscentPolar telemetry={telemetry} />
        </VisualizationSubpanel>

        <VisualizationSubpanel title="Ascent - Cartesian">
          <AscentCartesian telemetry={telemetry} />
        </VisualizationSubpanel>
      </div>
    </Panel>
  );
}

export default VisDatPanel;
