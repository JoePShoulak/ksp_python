function formatNumber(value, digits = 1) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return "—";
  }

  return number.toFixed(digits);
}

function formatMeters(value) {
  return `${formatNumber(value, 1)} m`;
}

function formatMetersPerSecond(value) {
  return `${formatNumber(value, 1)} m/s`;
}

function formatSeconds(value) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return "—";
  }

  const totalSeconds = Math.max(0, Math.floor(number));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  if (minutes <= 0) {
    return `${seconds}s`;
  }

  return `${minutes}m ${seconds.toString().padStart(2, "0")}s`;
}

function formatPercent(value) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return "—";
  }

  return `${Math.round(number * 100)}%`;
}

function TelemetryGroup({ title, children }) {
  return (
    <section className="numerical-telemetry-group">
      <h4>{title}</h4>
      <div className="numerical-telemetry-list">{children}</div>
    </section>
  );
}

function TelemetryRow({ label, value }) {
  return (
    <div className="numerical-telemetry-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function NumericalTelemetry({ telemetry }) {
  if (!telemetry) {
    return <p>No telemetry yet.</p>;
  }

  return (
    <div className="numerical-telemetry">
      <TelemetryGroup title="Flight">
        <TelemetryRow
          label="Altitude"
          value={formatMeters(telemetry.altitude)}
        />
        <TelemetryRow
          label="Surface Altitude"
          value={formatMeters(telemetry.surface_altitude)}
        />
        <TelemetryRow
          label="Speed"
          value={formatMetersPerSecond(telemetry.speed)}
        />
        <TelemetryRow
          label="Vertical Speed"
          value={formatMetersPerSecond(telemetry.vertical_speed)}
        />
      </TelemetryGroup>

      <TelemetryGroup title="Orbit">
        <TelemetryRow
          label="Apoapsis"
          value={formatMeters(telemetry.apoapsis)}
        />
        <TelemetryRow
          label="Periapsis"
          value={formatMeters(telemetry.periapsis)}
        />
        <TelemetryRow
          label="Time to Apoapsis"
          value={formatSeconds(telemetry.time_to_apoapsis)}
        />
        <TelemetryRow
          label="Time to Periapsis"
          value={formatSeconds(telemetry.time_to_periapsis)}
        />
      </TelemetryGroup>

      <TelemetryGroup title="Control">
        <TelemetryRow
          label="Throttle"
          value={formatPercent(telemetry.throttle)}
        />
        <TelemetryRow label="Stage" value={telemetry.stage ?? "—"} />
        <TelemetryRow
          label="Available Thrust"
          value={`${formatNumber(telemetry.available_thrust, 1)} N`}
        />
        <TelemetryRow
          label="Longitude"
          value={`${formatNumber(telemetry.longitude, 3)}°`}
        />
      </TelemetryGroup>
    </div>
  );
}

export default NumericalTelemetry;
