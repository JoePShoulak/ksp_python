import {
  EMPTY_VALUE,
  formatDegrees,
  formatGForce,
  formatMeters,
  formatMetersPerSecond,
  formatNewtons,
  formatNumber,
  formatPercent,
  formatRadiansAsDegrees,
  formatSeconds,
} from "../../utils/formatters";

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
      <strong title={value}>{value}</strong>
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
        <TelemetryRow
          label="Latitude"
          value={formatDegrees(telemetry.latitude)}
        />
        <TelemetryRow
          label="Heading"
          value={formatDegrees(telemetry.heading)}
        />
        <TelemetryRow
          label="Pitch"
          value={formatDegrees(telemetry.pitch)}
        />
        <TelemetryRow
          label="G Force"
          value={formatGForce(telemetry.g_force)}
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
        <TelemetryRow
          label="Inclination"
          value={formatRadiansAsDegrees(telemetry.inclination)}
        />
        <TelemetryRow
          label="Eccentricity"
          value={formatNumber(telemetry.eccentricity, 3)}
        />
        <TelemetryRow
          label="Period"
          value={formatSeconds(telemetry.orbital_period)}
        />
        <TelemetryRow
          label="Semi-major Axis"
          value={formatMeters(telemetry.semi_major_axis)}
        />
      </TelemetryGroup>

      <TelemetryGroup title="Control">
        <TelemetryRow
          label="Warp"
          value={telemetry.warp?.label ?? EMPTY_VALUE}
        />
        <TelemetryRow
          label="Throttle"
          value={formatPercent(telemetry.throttle)}
        />
        <TelemetryRow label="Stage" value={telemetry.stage ?? EMPTY_VALUE} />
        <TelemetryRow
          label="Available Thrust"
          value={formatNewtons(telemetry.available_thrust)}
        />
        <TelemetryRow
          label="Practical dV"
          value={formatMetersPerSecond(telemetry.delta_v)}
        />
        <TelemetryRow
          label="Current dV"
          value={formatMetersPerSecond(telemetry.delta_v_current)}
        />
        <TelemetryRow
          label="Vacuum dV"
          value={formatMetersPerSecond(telemetry.delta_v_vacuum)}
        />
        <TelemetryRow
          label="Longitude"
          value={formatDegrees(telemetry.longitude)}
        />
      </TelemetryGroup>
    </div>
  );
}

export default NumericalTelemetry;
