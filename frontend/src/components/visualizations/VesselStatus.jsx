function formatMet(totalSeconds) {
  const number = Number(totalSeconds);

  if (!Number.isFinite(number)) {
    return "T+ —";
  }

  const seconds = Math.max(0, Math.floor(number));

  const secondsPerMinute = 60;
  const secondsPerHour = 60 * secondsPerMinute;
  const secondsPerKerbinDay = 6 * secondsPerHour;
  const secondsPerKerbinYear = 426 * secondsPerKerbinDay;

  const years = Math.floor(seconds / secondsPerKerbinYear);
  const afterYears = seconds % secondsPerKerbinYear;

  const days = Math.floor(afterYears / secondsPerKerbinDay);
  const afterDays = afterYears % secondsPerKerbinDay;

  const hours = Math.floor(afterDays / secondsPerHour);
  const afterHours = afterDays % secondsPerHour;

  const minutes = Math.floor(afterHours / secondsPerMinute);
  const remainingSeconds = afterHours % secondsPerMinute;

  return `T+ ${years}y, ${days}d, ${hours.toString().padStart(2, "0")}:${minutes
    .toString()
    .padStart(2, "0")}:${remainingSeconds.toString().padStart(2, "0")}`;
}

function formatNumber(value, digits = 2) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return "—";
  }

  return number.toFixed(digits);
}

function formatPercent(value) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return "—";
  }

  return `${Math.round(number * 100)}%`;
}

function formatEnumValue(value) {
  if (!value) {
    return "—";
  }

  const rawValue = String(value);
  const lastPart = rawValue.split(".").at(-1);

  return lastPart
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\b\w/g, letter => letter.toUpperCase());
}

function formatResourceName(name) {
  if (!name) {
    return "—";
  }

  return String(name)
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2");
}

function StatusLight({ active, label }) {
  return (
    <div className={`status-light ${active ? "active" : ""}`} title={label}>
      {label}
    </div>
  );
}

function ResourceBar({ resource }) {
  const ratio = Math.max(0, Math.min(Number(resource.ratio) || 0, 1));
  const percent = `${ratio * 100}%`;

  return (
    <div className="resource-row">
      <div className="resource-label">{formatResourceName(resource.name)}</div>

      <div className="resource-bar">
        <div className="resource-fill" style={{ width: percent }} />
        <span>
          {formatNumber(resource.amount, 2)} / {formatNumber(resource.max, 2)}
        </span>
      </div>
    </div>
  );
}

function sortResources(resources) {
  const liquidFuelIndex = resources.findIndex(
    resource => resource.name === "LiquidFuel",
  );

  const oxidizerIndex = resources.findIndex(
    resource => resource.name === "Oxidizer",
  );

  if (liquidFuelIndex === -1 || oxidizerIndex === -1) {
    return resources;
  }

  const sortedResources = resources.filter(
    resource => resource.name !== "Oxidizer",
  );

  const newLiquidFuelIndex = sortedResources.findIndex(
    resource => resource.name === "LiquidFuel",
  );

  sortedResources.splice(newLiquidFuelIndex + 1, 0, resources[oxidizerIndex]);

  return sortedResources;
}

function VesselStatus({ telemetry }) {
  const comms = telemetry?.comms ?? {};
  const warp = telemetry?.warp ?? {};
  const resources = sortResources(telemetry?.resources ?? []);

  const hasCrew = Boolean(telemetry?.has_crew_control);
  const hasComm = Boolean(comms.display_has_connection ?? comms.has_connection);
  const hasData = Boolean(comms.display_has_data ?? comms.can_transmit_science);
  const hasSignal = Boolean(
    comms.display_has_signal ?? Number(comms.signal_strength) > 0,
  );

  if (!telemetry) {
    return <p>No telemetry yet.</p>;
  }

  return (
    <div className="vessel-status">
      <div className="vessel-status-column">
        <div className="met-display">{formatMet(telemetry.met)}</div>

        <div className="status-icon-row">
          <StatusLight active={hasCrew} label="Crew" />
          <StatusLight active={hasComm} label="Comm" />
          <StatusLight active={hasData} label="Data" />
          <StatusLight active={hasSignal} label="Signal" />
        </div>

        <div className="status-details">
          <div>
            <span>Vessel</span>
            <strong>{telemetry.vessel_name ?? "—"}</strong>
          </div>

          <div>
            <span>Crew</span>
            <strong>
              {telemetry.crew_count ?? "—"} / {telemetry.crew_capacity ?? "—"}
            </strong>
          </div>

          <div>
            <span>Connection</span>
            <strong>{hasComm ? "Connected" : "No connection"}</strong>
          </div>

          <div>
            <span>Data</span>
            <strong>{hasData ? "Available" : "Unavailable"}</strong>
          </div>

          <div>
            <span>Signal</span>
            <strong>{formatPercent(comms.signal_strength)}</strong>
          </div>

          <div>
            <span>Warp</span>
            <strong>{warp.label ?? "1x"}</strong>
          </div>

          <div>
            <span>Situation</span>
            <strong>{formatEnumValue(telemetry.situation)}</strong>
          </div>
        </div>
      </div>

      <div className="vessel-status-column">
        <h4>Resources</h4>

        {resources.length === 0 ? (
          <p>No resource data.</p>
        ) : (
          <div className="resource-list">
            {resources.map(resource => (
              <ResourceBar key={resource.name} resource={resource} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default VesselStatus;
