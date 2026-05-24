function CameraStream({ cameras }) {
  const selectedCamera = cameras?.selected;
  const streamUrl = selectedCamera?.stream_url;
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

export default CameraStream;
