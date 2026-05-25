import { useEffect } from "react";

import { reportViewport } from "../api/kspApi";

const VIEWPORT_REPORT_DELAY_MS = 150;
const VIEWPORT_CLIENT_ID_KEY = "kspViewportClientId";

function readViewport() {
  const width = window.visualViewport?.width ?? window.innerWidth;
  const height = window.visualViewport?.height ?? window.innerHeight;
  const report = {
    client_id: window.localStorage.getItem(VIEWPORT_CLIENT_ID_KEY),
    viewport_width: Math.round(width),
    viewport_height: Math.round(height),
    layout_width: window.innerWidth,
    layout_height: window.innerHeight,
    screen_width: window.screen?.width,
    screen_height: window.screen?.height,
    available_width: window.screen?.availWidth,
    available_height: window.screen?.availHeight,
    device_pixel_ratio: window.devicePixelRatio,
    orientation:
      window.screen?.orientation?.type ??
      (window.innerWidth >= window.innerHeight ? "landscape" : "portrait"),
    user_agent: window.navigator.userAgent,
  };

  if (!report.client_id) {
    report.client_id = `viewport-${Date.now()}-${Math.random()
      .toString(36)
      .slice(2)}`;
    window.localStorage.setItem(VIEWPORT_CLIENT_ID_KEY, report.client_id);
  }

  return report;
}

function logViewport(report) {
  console.info(
    "[KSP viewport]",
    `${report.viewport_width}x${report.viewport_height}`,
    `layout=${report.layout_width}x${report.layout_height}`,
    `screen=${report.screen_width}x${report.screen_height}`,
    `dpr=${report.device_pixel_ratio}`,
    report.orientation,
  );
}

export function useViewportReport() {
  useEffect(() => {
    let timeoutId = null;

    function sendViewport() {
      const report = readViewport();

      logViewport(report);
      reportViewport(report).catch(() => {});
    }

    function scheduleViewportReport() {
      window.clearTimeout(timeoutId);
      timeoutId = window.setTimeout(sendViewport, VIEWPORT_REPORT_DELAY_MS);
    }

    sendViewport();
    window.addEventListener("resize", scheduleViewportReport);
    window.visualViewport?.addEventListener("resize", scheduleViewportReport);
    window.screen?.orientation?.addEventListener?.("change", scheduleViewportReport);

    return () => {
      window.clearTimeout(timeoutId);
      window.removeEventListener("resize", scheduleViewportReport);
      window.visualViewport?.removeEventListener("resize", scheduleViewportReport);
      window.screen?.orientation?.removeEventListener?.(
        "change",
        scheduleViewportReport,
      );
    };
  }, []);
}
