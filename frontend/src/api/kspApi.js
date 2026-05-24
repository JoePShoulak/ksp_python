class ApiError extends Error {
  constructor(message, options = {}) {
    super(message);
    this.name = "ApiError";
    this.lowSignal = Boolean(options.lowSignal);
  }
}

function isHtmlResponse(text) {
  return text.trimStart().toLowerCase().startsWith("<!doctype html");
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const text = await response.text();
  const isActionRequest = url.startsWith("/api/actions/");

  let data;

  try {
    data = JSON.parse(text);
  } catch {
    if (isHtmlResponse(text) || isActionRequest) {
      throw new ApiError("Request did not complete", { lowSignal: true });
    }

    throw new ApiError(`Request failed: ${text.slice(0, 80)}`);
  }

  if (!response.ok || data.ok === false) {
    throw new ApiError(
      data.error || `Request failed with status ${response.status}`,
      { lowSignal: isActionRequest && response.status >= 400 },
    );
  }

  return data;
}

export async function runKspAction(actionId) {
  return fetchJson(`/api/actions/${actionId}`, {
    method: "POST",
  });
}

export async function abortKspAction() {
  return fetchJson("/api/abort", {
    method: "POST",
  });
}

export async function getTelemetry(options = {}) {
  return fetchJson("/api/telemetry", options);
}

export async function getMissionStatus(options = {}) {
  return fetchJson("/api/mission", options);
}
