import { useEffect, useRef } from "react";

import { reportViewport } from "../api/kspApi";

const VIEWPORT_REPORT_DELAY_MS = 250;
const VIEWPORT_REPORT_MIN_INTERVAL_MS = 2000;
const VIEWPORT_JITTER_PX = 20;
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
  const lastReportRef = useRef(null);

  useEffect(() => {
    let timeoutId = null;

    function reportsAreEffectivelyEqual(currentReport, previousReport) {
      if (!previousReport) {
        return false;
      }

      return (
        Math.abs(
          currentReport.viewport_width - previousReport.viewport_width,
        ) <= VIEWPORT_JITTER_PX &&
        Math.abs(
          currentReport.viewport_height - previousReport.viewport_height,
        ) <= VIEWPORT_JITTER_PX &&
        Math.abs(currentReport.layout_width - previousReport.layout_width) <=
          VIEWPORT_JITTER_PX &&
        Math.abs(currentReport.layout_height - previousReport.layout_height) <=
          VIEWPORT_JITTER_PX &&
        currentReport.device_pixel_ratio === previousReport.device_pixel_ratio &&
        currentReport.orientation === previousReport.orientation
      );
    }

    function sendViewport(force = false) {
      const report = readViewport();
      const now = Date.now();
      const lastReport = lastReportRef.current;

      if (
        !force &&
        lastReport &&
        now - lastReport.reportedAt < VIEWPORT_REPORT_MIN_INTERVAL_MS
      ) {
        return;
      }

      if (
        !force &&
        lastReport &&
        reportsAreEffectivelyEqual(report, lastReport.report)
      ) {
        return;
      }

      logViewport(report);
      lastReportRef.current = {
        report,
        reportedAt: now,
      };
      reportViewport(report).catch(() => {});
    }

    function scheduleViewportReport() {
      window.clearTimeout(timeoutId);
      timeoutId = window.setTimeout(sendViewport, VIEWPORT_REPORT_DELAY_MS);
    }

    sendViewport(true);
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
