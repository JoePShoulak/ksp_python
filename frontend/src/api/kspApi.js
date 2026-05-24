async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const text = await response.text();

  let data;

  try {
    data = JSON.parse(text);
  } catch {
    throw new Error(`Expected JSON from ${url}, but got: ${text.slice(0, 80)}`);
  }

  if (!response.ok || data.ok === false) {
    throw new Error(
      data.error || `Request failed with status ${response.status}`,
    );
  }

  return data;
}

export async function runKspAction(actionId) {
  return fetchJson(`/api/actions/${actionId}`, {
    method: "POST",
  });
}

export async function getTelemetry(options = {}) {
  return fetchJson("/api/telemetry", options);
}

export async function cycleCamera() {
  return fetchJson("/api/cameras/cycle", {
    method: "POST",
  });
}
