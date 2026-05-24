import Panel from "./Panel";
import VisualizationSubpanel from "./visualizations/VisualizationSubpanel";
import AscentCartesian from "./visualizations/AscentCartesian";
import AscentPolar from "./visualizations/AscentPolar";
import VesselStatus from "./visualizations/VesselStatus";

function VisDatPanel({ telemetry }) {
  return (
    <Panel title="Visualized Data">
      <div className="visualization-grid">
        <VisualizationSubpanel title="Vessel Status">
          <VesselStatus telemetry={telemetry} />
        </VisualizationSubpanel>

        <VisualizationSubpanel title="Ascent - Cartesian">
          <AscentCartesian telemetry={telemetry} />
        </VisualizationSubpanel>

        <VisualizationSubpanel title="Ascent - Polar">
          <AscentPolar telemetry={telemetry} />
        </VisualizationSubpanel>
      </div>
    </Panel>
  );
}

export default VisDatPanel;
