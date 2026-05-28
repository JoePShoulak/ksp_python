export const EMPTY_VALUE = "--";

export function formatNumber(value, digits = 1) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return EMPTY_VALUE;
  }

  return number.toFixed(digits);
}

export function formatMeters(value, digits = 1) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return EMPTY_VALUE;
  }

  if (Math.abs(number) >= 1000) {
    return `${formatNumber(number / 1000, digits)} km`;
  }

  return `${formatNumber(number, digits)} m`;
}

export function formatMetersPerSecond(value, digits = 1) {
  return `${formatNumber(value, digits)} m/s`;
}

export function formatDegrees(value, digits = 3) {
  return `${formatNumber(value, digits)} deg`;
}

export function formatRadiansAsDegrees(value, digits = 2) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return EMPTY_VALUE;
  }

  return formatDegrees((number * 180) / Math.PI, digits);
}

export function formatGForce(value, digits = 2) {
  return `${formatNumber(value, digits)} g`;
}

export function formatNewtons(value, digits = 1) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return EMPTY_VALUE;
  }

  if (Math.abs(number) >= 1000) {
    return `${formatNumber(number / 1000, digits)} kN`;
  }

  return `${formatNumber(number, digits)} N`;
}

export function formatSeconds(value) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return EMPTY_VALUE;
  }

  const totalSeconds = Math.max(0, Math.floor(number));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  if (minutes <= 0) {
    return `${seconds}s`;
  }

  return `${minutes}m ${seconds.toString().padStart(2, "0")}s`;
}

export function formatPercent(value) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return EMPTY_VALUE;
  }

  return `${Math.round(number * 100)}%`;
}

export function formatEnumValue(value) {
  if (!value) {
    return EMPTY_VALUE;
  }

  const rawValue = String(value);
  const lastPart = rawValue.split(".").at(-1);

  return lastPart
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\b\w/g, letter => letter.toUpperCase());
}

export function formatResourceName(name) {
  if (!name) {
    return EMPTY_VALUE;
  }

  return String(name)
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2");
}

export function formatMet(totalSeconds) {
  const number = Number(totalSeconds);

  if (!Number.isFinite(number)) {
    return `T+ ${EMPTY_VALUE}`;
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
