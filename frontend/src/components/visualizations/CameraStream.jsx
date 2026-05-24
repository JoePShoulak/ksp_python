function CameraStream({ cameras, isCycling, onCycleCamera }) {
  const selectedCamera = cameras?.selected;
  const cameraCount = cameras?.count ?? 0;
  const streamUrl = selectedCamera?.stream_url;
  const streamKind = selectedCamera?.stream_kind ?? "image";
  const cameraLabel = selectedCamera?.label ?? "Camera";

  return (
    <div className="camera-stream">
      <div className="camera-toolbar">
        <div>
          <p className="camera-label">{cameraLabel}</p>
          <p className="camera-meta">
            {cameraCount} {cameraCount === 1 ? "camera" : "cameras"} detected
          </p>
        </div>

        <button
          className="camera-cycle-button"
          type="button"
          onClick={onCycleCamera}
          disabled={isCycling || cameraCount < 2}>
          {isCycling ? "Cycling" : "Cycle"}
        </button>
      </div>

      <div className="camera-viewport">
        {streamUrl && streamKind === "iframe" && (
          <iframe title={cameraLabel} src={streamUrl} />
        )}

        {streamUrl && streamKind !== "iframe" && (
          <img src={streamUrl} alt={`${cameraLabel} stream`} />
        )}

        {!streamUrl && (
          <div className="camera-placeholder">
            <p>Camera stream unavailable</p>
            <span>Set KSP_CAMERA_STREAM_URL when the stream endpoint is known.</span>
          </div>
        )}
      </div>
    </div>
  );
}

export default CameraStream;
