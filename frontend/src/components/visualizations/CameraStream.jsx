function CameraStream({ cameras }) {
  const selectedCamera = cameras?.selected;
  const streamUrl = getReachableStreamUrl(selectedCamera?.stream_url);
  const streamKind = selectedCamera?.stream_kind ?? "image";

  return (
    <div className="camera-stream">
      <div className="camera-viewport">
        {streamUrl && streamKind === "iframe" && (
          <iframe title="Camera stream" src={streamUrl} />
        )}

        {streamUrl && streamKind !== "iframe" && (
          <img src={streamUrl} alt="Camera stream" />
        )}

        {!streamUrl && (
          <div className="camera-placeholder">
            <p>Camera stream unavailable</p>
            <span>
              Click Stream All in JRTI, then set KSP_CAMERA_STREAM_URL if this
              message remains.
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

function getReachableStreamUrl(streamUrl) {
  if (!streamUrl || typeof window === "undefined") {
    return streamUrl;
  }

  try {
    const url = new URL(streamUrl, window.location.href);

    if (["localhost", "127.0.0.1", "0.0.0.0"].includes(url.hostname)) {
      url.hostname = window.location.hostname;
    }

    return url.toString();
  } catch {
    return streamUrl;
  }
}

export default CameraStream;
