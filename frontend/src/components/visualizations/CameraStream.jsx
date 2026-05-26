import {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

const CAMERA_GRID_REFRESH_MS = 700;
const RECORDER_CHUNK_MS = 2000;
const RECORDER_CAPTURE_FPS = 24;
const RECORDER_VIDEO_BPS = 3_500_000;
const RECORDER_HEARTBEAT_MS = 5000;
const GROUP_STORAGE_KEY = "ksp-camera-recording-groups";
const GROUP_COLORS = ["#e0533a", "#58a6ff", "#3fb950", "#d29922"];
const CAMERA_IMAGE_RETRY_MS = 3000;

function CameraStream({ cameras }) {
  const [gridRefreshKey, setGridRefreshKey] = useState(0);
  const isPopout = isCameraPopout();
  const selectedCamera = cameras?.selected;
  const cameraList = cameras?.cameras ?? [];
  const streamUrl = getReachableStreamUrl(selectedCamera?.stream_url);
  const streamKind = getStreamKind(selectedCamera?.stream_kind, streamUrl);
  const showCameraGrid = cameraList.length > 0;

  useEffect(() => {
    if (!showCameraGrid) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      setGridRefreshKey(currentKey => currentKey + 1);
    }, CAMERA_GRID_REFRESH_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [showCameraGrid]);

  return (
    <div className="camera-stream">
      <div
        className={`camera-viewport ${showCameraGrid ? "has-camera-grid" : ""} ${
          isPopout ? "is-popout-grid" : ""
        }`}>
        {showCameraGrid && (
          <CameraGrid
            cameras={cameraList.slice(0, 6)}
            refreshKey={gridRefreshKey}
          />
        )}

        {streamUrl && streamKind === "iframe" && !isPopout && !showCameraGrid && (
          <iframe title="Camera stream" src={streamUrl} />
        )}

        {streamUrl && streamKind !== "iframe" && !showCameraGrid && (
          <img src={streamUrl} alt="Camera stream" />
        )}

        {!streamUrl && !showCameraGrid && (
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

function CameraGrid({ cameras, refreshKey }) {
  const cameraControllers = useRef(new Map());
  const [groupAssignments, setGroupAssignments] = useState(() => loadGroupAssignments());
  const [recordingStates, setRecordingStates] = useState({});

  const registerCameraController = useCallback((cameraId, controller) => {
    cameraControllers.current.set(cameraId, controller);

    return () => {
      cameraControllers.current.delete(cameraId);
    };
  }, []);

  const cycleCameraGroup = useCallback((cameraId) => {
    setGroupAssignments(currentAssignments => {
      const nextAssignments = { ...currentAssignments };
      const currentGroup = getGroupId(nextAssignments, cameraId);
      const nextGroup = currentGroup === null
        ? 0
        : currentGroup + 1 >= GROUP_COLORS.length
          ? null
          : currentGroup + 1;

      if (nextGroup === null) {
        delete nextAssignments[cameraId];
      } else {
        nextAssignments[cameraId] = nextGroup;
      }

      saveGroupAssignments(nextAssignments);
      return nextAssignments;
    });
  }, []);

  const groupSummaries = useMemo(() => (
    GROUP_COLORS.map((color, groupId) => {
      const members = cameras.filter(camera => getGroupId(groupAssignments, camera.id) === groupId);
      const activeCount = members.filter(camera => (
        ["recording", "paused"].includes(recordingStates[camera.id])
      )).length;

      return {
        activeCount,
        color,
        groupId,
        label: `G${groupId + 1}`,
        members,
      };
    })
  ), [cameras, groupAssignments, recordingStates]);

  const toggleGroupRecording = useCallback((groupId) => {
    const members = cameras.filter(camera => getGroupId(groupAssignments, camera.id) === groupId);
    const hasActiveRecording = members.some(camera => (
      cameraControllers.current.get(camera.id)?.isRecording()
    ));

    members.forEach(camera => {
      const controller = cameraControllers.current.get(camera.id);
      if (!controller) {
        return;
      }

      if (hasActiveRecording) {
        controller.stopRecording();
      } else {
        controller.startRecording();
      }
    });
  }, [cameras, groupAssignments]);

  const handleRecordingStateChange = useCallback((cameraId, state) => {
    setRecordingStates(currentStates => ({
      ...currentStates,
      [cameraId]: state,
    }));
  }, []);

  return (
    <div className="camera-grid-shell">
      {groupSummaries.some(group => group.members.length > 0) && (
        <div className="camera-group-bar">
          {groupSummaries.map(group => (
            group.members.length > 0 && (
              <button
                className={`camera-group-button ${
                  group.activeCount > 0 ? "is-recording" : ""
                }`}
                key={group.groupId}
                onClick={() => toggleGroupRecording(group.groupId)}
                style={{ "--group-color": group.color }}
                type="button">
                <span>{group.activeCount > 0 ? "■" : "●"}</span>
                {group.label}
                <small>{group.members.length}x</small>
                {group.activeCount > 0 ? "Stop" : "Rec"}
              </button>
            )
          ))}
        </div>
      )}

      <div className="camera-grid">
        {cameras.map(camera => (
          <CameraCard
            camera={camera}
            groupColor={getGroupColor(groupAssignments, camera.id)}
            groupId={getGroupId(groupAssignments, camera.id)}
            key={camera.id}
            onCycleGroup={cycleCameraGroup}
            onRecordingStateChange={handleRecordingStateChange}
            refreshKey={refreshKey}
            registerController={registerCameraController}
          />
        ))}
      </div>
    </div>
  );
}

function CameraCard({
  camera,
  groupColor,
  groupId,
  onCycleGroup,
  onRecordingStateChange,
  refreshKey,
  registerController,
}) {
  const [recordingState, setRecordingState] = useState({
    bytes: 0,
    error: null,
    filename: null,
    startedAt: null,
    state: "idle",
  });
  const [showMenu, setShowMenu] = useState(false);
  const [copiedLabel, setCopiedLabel] = useState(null);
  const recorderRef = useRef(null);
  const recordingStateRef = useRef(recordingState);

  useEffect(() => {
    recordingStateRef.current = recordingState;
  }, [recordingState]);

  const snapshotUrl = getRefreshableUrl(
    getReachableStreamUrl(camera.snapshot_url),
    refreshKey,
  );
  const streamUrl = getReachableStreamUrl(camera.stream_url);
  const recordingStreamUrl = getCameraRecordingStreamUrl(camera, streamUrl);
  const streamKind = snapshotUrl ? "image" : getStreamKind(camera.stream_kind, streamUrl);
  const cameraUrl = snapshotUrl || streamUrl;
  const isFeedAvailable = hasUsableCameraFeed(camera, cameraUrl);
  const supportsRecording = isRecordingSupported() && Boolean(recordingStreamUrl);
  const isActive = ["recording", "paused", "finalizing"].includes(recordingState.state);
  const isRecording = recordingState.state === "recording";
  const isPaused = recordingState.state === "paused";

  const updateRecordingState = useCallback((nextState) => {
    setRecordingState(currentState => {
      const resolvedState = {
        ...currentState,
        ...nextState,
      };
      recordingStateRef.current = resolvedState;
      onRecordingStateChange(camera.id, resolvedState.state);
      return resolvedState;
    });
  }, [camera.id, onRecordingStateChange]);

  const stopRecording = useCallback(() => {
    recorderRef.current?.stop();
  }, []);

  const startRecording = useCallback(() => {
    if (!supportsRecording || isActive) {
      return;
    }

    const recorder = new CameraRecorder({
      cameraId: camera.id,
      cameraName: camera.label,
      onStateChange: updateRecordingState,
      streamUrl: recordingStreamUrl,
    });

    recorderRef.current = recorder;
    recorder.start();
  }, [
    camera.id,
    camera.label,
    isActive,
    recordingStreamUrl,
    supportsRecording,
    updateRecordingState,
  ]);

  const pauseRecording = useCallback(() => {
    recorderRef.current?.pause();
  }, []);

  const resumeRecording = useCallback(() => {
    recorderRef.current?.resume();
  }, []);

  useEffect(() => registerController(camera.id, {
    isRecording: () => ["recording", "paused"].includes(recordingStateRef.current.state),
    startRecording,
    stopRecording,
  }), [camera.id, registerController, startRecording, stopRecording]);

  useEffect(() => () => {
    recorderRef.current?.emergencyFinalize();
    recorderRef.current = null;
  }, []);

  useEffect(() => {
    const finalize = () => {
      recorderRef.current?.emergencyFinalize();
    };

    window.addEventListener("pagehide", finalize);
    window.addEventListener("beforeunload", finalize);

    return () => {
      window.removeEventListener("pagehide", finalize);
      window.removeEventListener("beforeunload", finalize);
    };
  }, []);

  useEffect(() => {
    if (!showMenu) {
      return undefined;
    }

    const closeMenu = () => {
      setShowMenu(false);
    };

    window.addEventListener("pointerdown", closeMenu);

    return () => {
      window.removeEventListener("pointerdown", closeMenu);
    };
  }, [showMenu]);

  const copyCameraValue = useCallback(async (label, value) => {
    const ok = await copyText(value);
    setCopiedLabel(ok ? label : "Copy failed");
    window.setTimeout(() => setCopiedLabel(null), 1200);
  }, []);

  return (
    <article
      className={`camera-card ${isActive ? "is-recording" : ""} ${
        isFeedAvailable ? "" : "is-standby"
      }`}
      style={groupColor ? { "--group-color": groupColor } : undefined}>
      <button
        className="camera-card-group-strip"
        onClick={() => onCycleGroup(camera.id)}
        title="Assign recording group"
        type="button" />

      <div className="camera-card-media">
        {isFeedAvailable && streamKind === "iframe" && (
          <iframe title={camera.label} src={cameraUrl} />
        )}

        {isFeedAvailable && streamKind !== "iframe" && (
          <StableCameraImage
            alt={camera.label}
            src={cameraUrl}
            unavailableLabel={getCameraUnavailableLabel(camera)}
          />
        )}

        {!isFeedAvailable && (
          <CameraStandby label={getCameraUnavailableLabel(camera)} />
        )}

        {isActive && <span className="camera-recording-badge">REC</span>}
      </div>

      <div className="camera-card-footer">
        <div className="camera-card-label-row">
          <strong>{camera.label}</strong>
          {Number.isFinite(camera.viewer_count) && (
            <span>{camera.viewer_count} watching</span>
          )}
        </div>

        <div className="camera-card-actions">
          {streamUrl && (
            <a
              className={`camera-card-action ${
                camera.streaming ? "is-watch" : "is-watch-disabled"
              }`}
              href={streamUrl}
              target="_blank"
              rel="noreferrer">
              Watch
            </a>
          )}

          <button
            className={`camera-card-action is-record ${isActive ? "is-active" : ""}`}
            type="button"
            onClick={isActive ? stopRecording : startRecording}
            disabled={!supportsRecording || recordingState.state === "finalizing"}>
            <span className="record-dot" />
            {isActive ? "Stop" : "Record"}
          </button>

          {isActive && (
            <button
              className="camera-card-action"
              type="button"
              onClick={isPaused ? resumeRecording : pauseRecording}
              disabled={recordingState.state === "finalizing"}>
              {isPaused ? "Resume" : "Pause"}
            </button>
          )}

          <button
            className="camera-card-action"
            type="button"
            onClick={() => onCycleGroup(camera.id)}
            style={groupColor ? { borderColor: groupColor, color: groupColor } : undefined}>
            {groupId === null ? "Grp" : `G${groupId + 1}`}
          </button>

          <div className="camera-card-menu-wrapper" onPointerDown={event => event.stopPropagation()}>
            <button
              className="camera-card-action"
              type="button"
              onClick={() => setShowMenu(currentValue => !currentValue)}>
              ...
            </button>

            {showMenu && (
              <div className="camera-card-menu">
                {streamUrl && (
                  <button
                    type="button"
                    onClick={() => copyCameraValue("Viewer copied", absoluteUrl(streamUrl))}>
                    Copy Viewer URL
                  </button>
                )}
                {recordingStreamUrl && (
                  <button
                    type="button"
                    onClick={() => copyCameraValue("Stream copied", absoluteUrl(recordingStreamUrl))}>
                    Copy Stream URL
                  </button>
                )}
                {copiedLabel && <span>{copiedLabel}</span>}
              </div>
            )}
          </div>
        </div>

        <div className="camera-card-status-row">
          <span className={`camera-card-status ${
            isRecording ? "is-recording" : isPaused ? "is-paused" : ""
          }`}>
            {formatRecordingStatus(recordingState, camera)}
          </span>
          {recordingState.bytes > 0 && (
            <span className="camera-card-recording-size">
              {formatBytes(recordingState.bytes)}
            </span>
          )}
        </div>
      </div>
    </article>
  );
}

function StableCameraImage({ alt, src, unavailableLabel }) {
  const [loadedSrc, setLoadedSrc] = useState(null);
  const [retryBlocked, setRetryBlocked] = useState(false);
  const retryTimerRef = useRef(null);
  const shouldAttemptLoad = src && !retryBlocked;

  useEffect(() => () => {
    window.clearTimeout(retryTimerRef.current);
  }, []);

  if (!src || !shouldAttemptLoad) {
    return loadedSrc
      ? <img src={loadedSrc} alt={alt} />
      : <CameraStandby label={unavailableLabel} />;
  }

  return (
    <>
      {loadedSrc && loadedSrc !== src && <img src={loadedSrc} alt={alt} aria-hidden="true" />}
      <img
        className={!loadedSrc || loadedSrc !== src ? "is-loading-next-frame" : ""}
        src={src}
        alt={alt}
        onLoad={() => {
          setLoadedSrc(src);
          setRetryBlocked(false);
          window.clearTimeout(retryTimerRef.current);
        }}
        onError={() => {
          setRetryBlocked(true);
          window.clearTimeout(retryTimerRef.current);
          retryTimerRef.current = window.setTimeout(() => {
            setRetryBlocked(false);
          }, CAMERA_IMAGE_RETRY_MS);
        }}
      />
      {!loadedSrc && <CameraStandby label={unavailableLabel} />}
    </>
  );
}

function CameraStandby({ label }) {
  return (
    <div className="camera-card-standby" role="status">
      <span>{label}</span>
    </div>
  );
}

function getRefreshableUrl(url, refreshKey) {
  if (!url) {
    return null;
  }

  try {
    const refreshableUrl = new URL(url, window.location.href);
    refreshableUrl.searchParams.set("_", refreshKey);
    return refreshableUrl.toString();
  } catch {
    return url;
  }
}

function hasUsableCameraFeed(camera, cameraUrl) {
  if (!cameraUrl) {
    return false;
  }

  if (camera.snapshot_url) {
    return true;
  }

  if (camera.source === "jrti" && camera.streaming === false) {
    return false;
  }

  return true;
}

function getCameraUnavailableLabel(camera) {
  if (camera.source === "jrti" && camera.streaming === false) {
    return "Waiting for stream";
  }

  return "Stream unavailable";
}

function loadGroupAssignments() {
  try {
    const savedAssignments = JSON.parse(window.localStorage.getItem(GROUP_STORAGE_KEY) || "{}");
    return savedAssignments && typeof savedAssignments === "object" ? savedAssignments : {};
  } catch {
    return {};
  }
}

function saveGroupAssignments(assignments) {
  try {
    window.localStorage.setItem(GROUP_STORAGE_KEY, JSON.stringify(assignments));
  } catch {
    // Ignore private browsing or storage quota failures.
  }
}

function getGroupId(assignments, cameraId) {
  const groupId = assignments[cameraId];

  return Number.isInteger(groupId) && groupId >= 0 && groupId < GROUP_COLORS.length
    ? groupId
    : null;
}

function getGroupColor(assignments, cameraId) {
  const groupId = getGroupId(assignments, cameraId);

  return groupId === null ? null : GROUP_COLORS[groupId];
}

function isRecordingSupported() {
  return (
    typeof MediaRecorder !== "undefined" &&
    typeof HTMLCanvasElement !== "undefined" &&
    typeof HTMLCanvasElement.prototype.captureStream === "function" &&
    pickRecordingMimeType() !== null
  );
}

function pickRecordingMimeType() {
  if (typeof MediaRecorder === "undefined") {
    return null;
  }

  const candidates = navigator.userAgent.includes("Firefox/")
    ? [
        "video/webm;codecs=vp9",
        "video/webm;codecs=vp8",
        "video/webm",
      ]
    : [
        "video/mp4;codecs=avc1.42E01E",
        "video/mp4;codecs=avc1",
        "video/webm;codecs=vp9",
        "video/webm;codecs=vp8",
        "video/webm",
      ];

  return candidates.find(mimeType => MediaRecorder.isTypeSupported(mimeType)) ?? null;
}

function getCameraRecordingStreamUrl(camera, fallbackStreamUrl) {
  if (camera.source === "jrti" && camera.id !== undefined && camera.id !== null) {
    return `/camera/${encodeURIComponent(camera.id)}/stream`;
  }

  return fallbackStreamUrl;
}

function buildRecordingFilename(cameraName, cameraId, mimeType) {
  const safeName = (cameraName || "camera")
    .replace(/[\\/:*?"<>|\s]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 80) || "camera";
  const date = new Date();
  const pad = value => String(value).padStart(2, "0");
  const stamp = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
    + `_${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`;
  const extension = mimeType?.toLowerCase().includes("mp4") ? "mp4" : "webm";

  return `${safeName}__cam${cameraId}__${stamp}.${extension}`;
}

function buildRecordingSessionId(cameraId) {
  return `cam${cameraId}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function recordingAppendUrl(sessionId, filename) {
  return `/recordings/${sessionId}/append?name=${encodeURIComponent(filename)}`;
}

function recordingFinalizeUrl(sessionId, filename) {
  return `/recordings/${sessionId}/finalize?name=${encodeURIComponent(filename)}`;
}

function formatBytes(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }

  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  if (bytes < 1024 * 1024 * 1024) {
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }

  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function formatDuration(ms) {
  const seconds = Math.floor(ms / 1000);
  const minutes = String(Math.floor(seconds / 60)).padStart(2, "0");
  const remainingSeconds = String(seconds % 60).padStart(2, "0");

  return `${minutes}:${remainingSeconds}`;
}

function formatRecordingStatus(recordingState, camera) {
  if (recordingState.error) {
    return recordingState.error;
  }

  if (recordingState.state === "recording") {
    return `Recording ${formatDuration(Date.now() - recordingState.startedAt)}`;
  }

  if (recordingState.state === "paused") {
    return "Paused";
  }

  if (recordingState.state === "finalizing") {
    return "Saving...";
  }

  if (camera.viewer_count > 0) {
    return "Watching";
  }

  return camera.streaming ? "Streaming" : "Idle";
}

function absoluteUrl(url) {
  try {
    return new URL(url, window.location.href).toString();
  } catch {
    return url;
  }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

async function uploadRecordingChunk(sessionId, filename, blob, mimeType) {
  const response = await fetch(recordingAppendUrl(sessionId, filename), {
    method: "POST",
    headers: { "Content-Type": mimeType },
    body: blob,
  });

  if (!response.ok) {
    throw new Error(`Upload failed: ${response.status}`);
  }
}

function heartbeatRecording(sessionId, filename) {
  fetch(recordingAppendUrl(sessionId, filename), {
    method: "POST",
    body: "",
  }).catch(() => {});
}

async function finalizeRecording(sessionId, filename) {
  const response = await fetch(recordingFinalizeUrl(sessionId, filename), {
    method: "POST",
    keepalive: true,
  });

  if (!response.ok) {
    throw new Error(`Finalize failed: ${response.status}`);
  }
}

function finalizeRecordingBeacon(sessionId, filename) {
  fetch(recordingFinalizeUrl(sessionId, filename), {
    method: "POST",
    keepalive: true,
  }).catch(() => {});
}

async function saveLocalBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 60000);
}

class MjpegStreamReader {
  constructor(streamUrl, onFrame) {
    this.streamUrl = streamUrl;
    this.onFrame = onFrame;
    this.fetchAbort = null;
    this.retryTimer = null;
  }

  start() {
    this.pump();
  }

  stop() {
    this.fetchAbort?.abort();
    this.fetchAbort = null;
    window.clearTimeout(this.retryTimer);
    this.retryTimer = null;
  }

  async pump() {
    this.fetchAbort = new AbortController();

    try {
      const response = await fetch(`${this.streamUrl}?r=${Date.now()}`, {
        signal: this.fetchAbort.signal,
      });
      const reader = response.body.getReader();
      let buffer = new Uint8Array(0);

      const flush = async () => {
        while (true) {
          let startOfImage = -1;
          for (let index = 0; index < buffer.length - 1; index += 1) {
            if (buffer[index] === 0xff && buffer[index + 1] === 0xd8) {
              startOfImage = index;
              break;
            }
          }

          if (startOfImage === -1) {
            break;
          }

          let endOfImage = -1;
          for (let index = startOfImage + 2; index < buffer.length - 1; index += 1) {
            if (buffer[index] === 0xff && buffer[index + 1] === 0xd9) {
              endOfImage = index;
              break;
            }
          }

          if (endOfImage === -1) {
            break;
          }

          const frame = buffer.slice(startOfImage, endOfImage + 2);
          buffer = buffer.slice(endOfImage + 2);
          const shouldContinue = await this.onFrame(frame);

          if (shouldContinue === false) {
            break;
          }
        }
      };

      while (true) {
        const { done, value } = await reader.read();

        if (done) {
          break;
        }

        const nextBuffer = new Uint8Array(buffer.length + value.length);
        nextBuffer.set(buffer);
        nextBuffer.set(value, buffer.length);
        buffer = nextBuffer;
        await flush();
      }
    } catch (error) {
      if (error.name === "AbortError") {
        return;
      }

      this.retryTimer = window.setTimeout(() => this.pump(), 1000);
    }
  }
}

class CameraRecorder {
  constructor({ cameraId, cameraName, streamUrl, onStateChange }) {
    this.cameraId = cameraId;
    this.cameraName = cameraName;
    this.streamUrl = streamUrl;
    this.onStateChange = onStateChange;
    this.state = "idle";
    this.bytes = 0;
    this.startedAt = null;
    this.mimeType = null;
    this.mediaRecorder = null;
    this.canvas = null;
    this.context = null;
    this.reader = null;
    this.stream = null;
    this.sessionId = null;
    this.filename = null;
    this.pendingUploads = Promise.resolve();
    this.heartbeatTimer = null;
    this.localChunks = [];
    this.aborted = false;
    this.isLocal = ["localhost", "127.0.0.1"].includes(window.location.hostname);
  }

  get isActive() {
    return this.state === "recording" || this.state === "paused";
  }

  start() {
    if (this.isActive) {
      return;
    }

    this.mimeType = pickRecordingMimeType();

    if (!this.mimeType) {
      this.notify({ error: "Recording unsupported" });
      return;
    }

    this.sessionId = buildRecordingSessionId(this.cameraId);
    this.filename = buildRecordingFilename(this.cameraName, this.cameraId, this.mimeType);
    this.bytes = 0;
    this.startedAt = Date.now();
    this.aborted = false;
    this.setState("recording");
    this.startHeartbeat();
    this.startCanvasPump();
  }

  pause() {
    if (this.state !== "recording" || !this.mediaRecorder) {
      return;
    }

    try {
      this.mediaRecorder.pause();
      this.setState("paused");
    } catch {
      // MediaRecorder can reject pause during startup; leave state unchanged.
    }
  }

  resume() {
    if (this.state !== "paused" || !this.mediaRecorder) {
      return;
    }

    try {
      this.mediaRecorder.resume();
      this.setState("recording");
    } catch {
      // MediaRecorder can reject resume during shutdown; leave state unchanged.
    }
  }

  stop() {
    if (!this.isActive) {
      return;
    }

    this.finalize();
  }

  emergencyFinalize() {
    if (!this.isLocal || this.state === "idle" || !this.sessionId) {
      return;
    }

    this.aborted = true;
    this.stopHeartbeat();

    try {
      if (this.mediaRecorder && this.mediaRecorder.state !== "inactive") {
        this.mediaRecorder.stop();
      }
    } catch {
      // Best effort while the page is closing.
    }

    finalizeRecordingBeacon(this.sessionId, this.filename);
  }

  startCanvasPump() {
    this.reader = new MjpegStreamReader(this.streamUrl, async (frame) => {
      if (this.state === "idle" || this.state === "finalizing") {
        return false;
      }

      const bitmap = await createImageBitmap(new Blob([frame], { type: "image/jpeg" }));

      if (!this.canvas) {
        this.canvas = document.createElement("canvas");
        this.canvas.width = bitmap.width;
        this.canvas.height = bitmap.height;
        this.context = this.canvas.getContext("2d");
        this.context.drawImage(bitmap, 0, 0);
        this.stream = this.canvas.captureStream(RECORDER_CAPTURE_FPS);
        this.mediaRecorder = new MediaRecorder(this.stream, {
          mimeType: this.mimeType,
          videoBitsPerSecond: RECORDER_VIDEO_BPS,
        });
        this.mediaRecorder.addEventListener("dataavailable", event => this.onChunk(event));
        this.mediaRecorder.addEventListener("error", () => this.finalize());
        this.mediaRecorder.start(RECORDER_CHUNK_MS);
      } else if (this.context) {
        this.context.drawImage(bitmap, 0, 0, this.canvas.width, this.canvas.height);
        this.stream?.getVideoTracks()[0]?.requestFrame?.();
      }

      bitmap.close();
      return true;
    });
    this.reader.start();
  }

  stopCanvasPump() {
    this.reader?.stop();
    this.reader = null;
  }

  onChunk(event) {
    const blob = event.data;

    if (!blob || blob.size === 0 || this.aborted) {
      return;
    }

    this.bytes += blob.size;

    if (!this.isLocal) {
      this.localChunks.push(blob);
      this.notify();
      return;
    }

    const sessionId = this.sessionId;
    const filename = this.filename;

    this.pendingUploads = this.pendingUploads.then(async () => {
      if (this.aborted) {
        return;
      }

      await uploadRecordingChunk(sessionId, filename, blob, this.mimeType);
      this.notify();
    }).catch(error => {
      this.notify({ error: error.message || "Upload failed" });
    });
  }

  async finalize() {
    if (this.state === "finalizing" || this.state === "idle") {
      return;
    }

    this.setState("finalizing");
    this.stopCanvasPump();

    try {
      if (this.mediaRecorder && this.mediaRecorder.state !== "inactive") {
        await new Promise(resolve => {
          const timer = window.setTimeout(resolve, 3000);
          const done = () => {
            window.clearTimeout(timer);
            resolve();
          };

          this.mediaRecorder.addEventListener("stop", done, { once: true });

          try {
            this.mediaRecorder.requestData();
            this.mediaRecorder.stop();
          } catch {
            done();
          }
        });
      }

      if (this.isLocal) {
        await this.pendingUploads;
        await finalizeRecording(this.sessionId, this.filename);
      } else if (this.localChunks.length > 0) {
        await saveLocalBlob(new Blob(this.localChunks, { type: this.mimeType }), this.filename);
      }
    } catch (error) {
      this.notify({ error: error.message || "Save failed" });
    } finally {
      this.cleanup();
      this.setState("idle");
    }
  }

  startHeartbeat() {
    if (this.heartbeatTimer || !this.isLocal) {
      return;
    }

    this.heartbeatTimer = window.setInterval(() => {
      if (!this.aborted && this.isActive) {
        heartbeatRecording(this.sessionId, this.filename);
      }
    }, RECORDER_HEARTBEAT_MS);
  }

  stopHeartbeat() {
    window.clearInterval(this.heartbeatTimer);
    this.heartbeatTimer = null;
  }

  cleanup() {
    this.stopCanvasPump();
    this.stopHeartbeat();

    if (this.stream) {
      this.stream.getTracks().forEach(track => {
        try {
          track.stop();
        } catch {
          // Best effort.
        }
      });
    }

    this.mediaRecorder = null;
    this.canvas = null;
    this.context = null;
    this.stream = null;
    this.localChunks = [];
  }

  setState(state) {
    this.state = state;
    this.notify();
  }

  notify(extras = {}) {
    this.onStateChange({
      bytes: this.bytes,
      error: null,
      filename: this.filename,
      startedAt: this.startedAt,
      state: this.state,
      ...extras,
    });
  }
}

function isCameraPopout() {
  if (typeof window === "undefined") {
    return false;
  }

  return new URLSearchParams(window.location.search).get("popout") === "ksp-camera-feed";
}

function getStreamKind(streamKind, streamUrl) {
  if (streamKind === "iframe") {
    return "iframe";
  }

  if (!streamUrl) {
    return streamKind ?? "image";
  }

  try {
    const url = new URL(streamUrl, window.location.href);
    const path = url.pathname.toLowerCase();

    if (
      path.endsWith(".html") ||
      path === "/" ||
      url.port === "8080"
    ) {
      return "iframe";
    }
  } catch {
    return streamKind ?? "image";
  }

  return streamKind ?? "image";
}

function getReachableStreamUrl(streamUrl) {
  if (!streamUrl || typeof window === "undefined") {
    return streamUrl;
  }

  try {
    const url = new URL(streamUrl, window.location.href);

    if (url.port === "8080") {
      return `/jrti${url.pathname}${url.search}${url.hash}`;
    }

    if (["localhost", "127.0.0.1", "0.0.0.0"].includes(url.hostname)) {
      url.hostname = window.location.hostname;
    }

    return url.toString();
  } catch {
    return streamUrl;
  }
}

function camerasAreEquivalent(previousProps, nextProps) {
  const previousCamera = previousProps.cameras?.selected;
  const nextCamera = nextProps.cameras?.selected;
  const previousCameras = previousProps.cameras?.cameras ?? [];
  const nextCameras = nextProps.cameras?.cameras ?? [];

  return (
    previousCamera?.stream_url === nextCamera?.stream_url &&
    previousCamera?.stream_kind === nextCamera?.stream_kind &&
    previousCameras.length === nextCameras.length &&
    previousCameras.every((camera, index) => (
      camera.id === nextCameras[index]?.id &&
      camera.stream_url === nextCameras[index]?.stream_url &&
      camera.snapshot_url === nextCameras[index]?.snapshot_url &&
      camera.streaming === nextCameras[index]?.streaming &&
      camera.viewer_count === nextCameras[index]?.viewer_count
    ))
  );
}

export default memo(CameraStream, camerasAreEquivalent);
