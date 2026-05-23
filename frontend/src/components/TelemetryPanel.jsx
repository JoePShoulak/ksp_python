import { useEffect, useState } from "react";
import Panel from "./Panel";
import { getTelemetry } from "../api/kspApi";

function formatNumber(value, digits = 1) {
  if (typeof value !== "number") {
    return "—";
  }

  return value.toFixed(digits);
}

function TelemetryPanel() {
  const [telemetry, setTelemetry] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const intervalId = setInterval(() => {
      getTelemetry()
        .then(data => {
          setTelemetry(data.telemetry);
          setError(null);
        })
        .catch(error => {
          setError(error.message);
        });
    }, 250);

    return () => {
      clearInterval(intervalId);
    };
  }, []);

  return (
    <Panel title="Telemetry">
      {error && <p>Error: {error}</p>}

      {!telemetry ? (
        <p>No telemetry yet.</p>
      ) : (
        <div className="telemetry-grid">
          <div>Status</div>
          <div>{telemetry.status ?? "—"}</div>

          <div>Altitude</div>
          <div>{formatNumber(telemetry.altitude)} m</div>

          <div>Surface Altitude</div>
          <div>{formatNumber(telemetry.surface_altitude)} m</div>

          <div>Vertical Speed</div>
          <div>{formatNumber(telemetry.vertical_speed)} m/s</div>

          <div>Speed</div>
          <div>{formatNumber(telemetry.speed)} m/s</div>

          <div>Stage</div>
          <div>{telemetry.stage ?? "—"}</div>

          <div>Throttle</div>
          <div>{formatNumber(telemetry.throttle, 2)}</div>
        </div>
      )}
    </Panel>
  );
}

export default TelemetryPanel;
