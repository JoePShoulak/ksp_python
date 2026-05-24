import Panel from "./Panel";
import KspSketch from "./KspSketch";

function VisDatPanel({ telemetry }) {
  return (
    <Panel title="Visualized Data">
      <KspSketch telemetry={telemetry} width={600} height={300} />
    </Panel>
  );
}

export default VisDatPanel;
