import {
  EMPTY_VALUE,
  formatEnumValue,
  formatMet,
  formatNumber,
  formatPercent,
  formatResourceName,
} from "../../utils/formatters";

function StatusLight({ active, label }) {
  const stateLabel = active ? "active" : "inactive";

  return (
    <div
      className={`status-light ${active ? "active" : ""}`}
      role="status"
      aria-label={`${label}: ${stateLabel}`}
      title={`${label}: ${stateLabel}`}>
      {label}
    </div>
  );
}

function ResourceBar({ resource }) {
  const ratio = Math.max(0, Math.min(Number(resource.ratio) || 0, 1));
  const percent = `${ratio * 100}%`;
  const label = formatResourceName(resource.name);
  const amount = formatNumber(resource.amount, 2);
  const max = formatNumber(resource.max, 2);
  const valueLabel = `${amount} / ${max}`;

  return (
    <div className="resource-row">
      <div className="resource-label">{label}</div>

      <div className="resource-bar" title={`${label}: ${valueLabel}`}>
        <div className="resource-fill" style={{ width: percent }} />
        <span>{formatPercent(ratio)}</span>
      </div>

      <div className="resource-value" title={valueLabel}>
        {valueLabel}
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
            <strong>{telemetry.vessel_name ?? EMPTY_VALUE}</strong>
          </div>

          <div>
            <span>Crew</span>
            <strong>
              {telemetry.crew_count ?? EMPTY_VALUE} /{" "}
              {telemetry.crew_capacity ?? EMPTY_VALUE}
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
