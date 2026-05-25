import { useEffect, useState } from "react";

function FullscreenButton() {
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    function syncFullscreenState() {
      setIsFullscreen(Boolean(getFullscreenElement()));
    }

    syncFullscreenState();
    document.addEventListener("fullscreenchange", syncFullscreenState);
    document.addEventListener("webkitfullscreenchange", syncFullscreenState);

    return () => {
      document.removeEventListener("fullscreenchange", syncFullscreenState);
      document.removeEventListener("webkitfullscreenchange", syncFullscreenState);
    };
  }, []);

  async function handleToggleFullscreen() {
    const fullscreenElement = getFullscreenElement();

    if (fullscreenElement) {
      await exitFullscreen().catch(() => {});
      return;
    }

    await requestFullscreen(document.documentElement).catch(() => {});
  }

  return (
    <button
      className="fullscreen-button"
      type="button"
      onClick={handleToggleFullscreen}
      aria-label={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
      title={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}>
      <span aria-hidden="true">{isFullscreen ? "x" : "[ ]"}</span>
      <span>{isFullscreen ? "Exit" : "Fullscreen"}</span>
    </button>
  );
}

function getFullscreenElement() {
  return document.fullscreenElement ?? document.webkitFullscreenElement ?? null;
}

function requestFullscreen(element) {
  const request = element.requestFullscreen ?? element.webkitRequestFullscreen;
  return request?.call(element) ?? Promise.resolve();
}

function exitFullscreen() {
  const exit = document.exitFullscreen ?? document.webkitExitFullscreen;
  return exit?.call(document) ?? Promise.resolve();
}

export default FullscreenButton;
