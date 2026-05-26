export function buildPopoutId(value) {
  return `ksp-${String(value).replace(/\W+/g, "-").toLowerCase()}`;
}
