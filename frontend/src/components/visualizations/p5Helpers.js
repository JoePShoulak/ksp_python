export const DEFAULT_CANVAS_SIZE = 600;

export function getFiniteNumber(value, fallback = 0) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return fallback;
  }

  return number;
}
