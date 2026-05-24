import { useEffect, useState } from "react";
import Panel from "./Panel";
import { getTelemetry } from "../api/kspApi";

function formatNumber(value, digits = 1) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return "—";
  }

  return number.toFixed(digits);
}

function TelemetryPanel({ enabled, onToggle, telemetry, setTelemetry }) {
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const intervalId = setInterval(() => {
      getTelemetry()
        .then(data => {
          setTelemetry(data.telemetry);
          setError(null);
        })
        .catch(error => {
          setError(error.message);
        });
    }, 50);

    return () => {
      clearInterval(intervalId);
    };
  }, [enabled, setTelemetry]);

  return (
    <Panel title="Telemetry">
      <div className="telemetry-controls">
        <p>
          Polling is <strong>{enabled ? "enabled" : "disabled"}</strong>.
        </p>

        <button onClick={onToggle}>
          {enabled ? "Disable Telemetry" : "Enable Telemetry"}
        </button>
      </div>

      {!enabled && <p>Telemetry polling is disabled.</p>}

      {enabled && error && <p>Error: {error}</p>}

      {!telemetry ? (
        <p>No telemetry yet.</p>
      ) : (
        <div className="telemetry-grid">
          <div>Status</div>
          <div>{telemetry.status ?? "—"}</div>

          <div>Warning</div>
          <div>{telemetry.warning ?? "—"}</div>

          <div>Apoapsis</div>
          <div>{formatNumber(telemetry.apoapsis)} m</div>

          <div>Periapsis</div>
          <div>{formatNumber(telemetry.periapsis)} m</div>

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
