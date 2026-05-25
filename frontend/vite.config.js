import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const JRTI_TARGET = "http://192.168.20.104:8080";
const JRTI_SNAPSHOT_REFRESH_MS = 500;

export default defineConfig({
  plugins: [react(), jrtiConfigOverride()],
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:5000",
        changeOrigin: true,
      },
      "/jrti": {
        target: JRTI_TARGET,
        changeOrigin: true,
        rewrite: path => path.replace(/^\/jrti/, ""),
      },
      "/camera": {
        target: JRTI_TARGET,
        changeOrigin: true,
      },
      "/cameras": {
        target: JRTI_TARGET,
        changeOrigin: true,
      },
      "/session": {
        target: JRTI_TARGET,
        changeOrigin: true,
      },
      "/viewer.html": {
        target: JRTI_TARGET,
        changeOrigin: true,
      },
      "/js": {
        target: JRTI_TARGET,
        changeOrigin: true,
      },
      "/css": {
        target: JRTI_TARGET,
        changeOrigin: true,
      },
      "/images": {
        target: JRTI_TARGET,
        changeOrigin: true,
      },
      "/recordings": {
        target: JRTI_TARGET,
        changeOrigin: true,
      },
    },
  },
});

function patchJrtiConfig(source) {
  return source.replace(
    /export const SNAPSHOT_REFRESH_MS = \d+;/,
    `export const SNAPSHOT_REFRESH_MS = ${JRTI_SNAPSHOT_REFRESH_MS};`,
  );
}

function patchJrtiCameraCard(source) {
  return source
    .replace(
      "this._snapshot.start();",
      "this._snapshot.start();\n        if (this.streaming) this._startLivePreview();",
    )
    .replace(
      "if (nameEl) nameEl.textContent = this.name;\n\n        const newViewerCount",
      "if (nameEl) nameEl.textContent = this.name;\n\n        if (this.streaming && !this.recorder?.isActive) this._startLivePreview();\n        else if (!this.streaming) this._stopLivePreview();\n\n        const newViewerCount",
    )
    .replace(
      "if (this._viewerCount > 0) {\n                    statusEl.textContent = 'Watching';\n                    this._startLivePreview();\n                } else {",
      "if (this.streaming || this._viewerCount > 0) {\n                    statusEl.textContent = this._viewerCount > 0 ? 'Watching' : 'Live';\n                    this._startLivePreview();\n                } else {",
    )
    .replace(
      "if (this._viewerCount > 0 && !recActive) {",
      "if ((this.streaming || this._viewerCount > 0) && !recActive) {",
    )
    .replace(
      "} else if (this._viewerCount === 0) {",
      "} else if (!this.streaming && this._viewerCount === 0) {",
    )
    .replace(
      "if (statusEl) statusEl.textContent = this._viewerCount > 0 ? 'Watching' : 'Idle';",
      "if (statusEl) statusEl.textContent = this._viewerCount > 0 ? 'Watching' : (this.streaming ? 'Live' : 'Idle');",
    );
}

function jrtiConfigOverride() {
  return {
    name: "jrti-config-override",
    configureServer(server) {
      server.middlewares.use("/js/config.js", async (_request, response, next) => {
        try {
          const jrtiResponse = await fetch(`${JRTI_TARGET}/js/config.js`);

          if (!jrtiResponse.ok) {
            next();
            return;
          }

          response.setHeader("content-type", "application/javascript; charset=utf-8");
          response.end(patchJrtiConfig(await jrtiResponse.text()));
        } catch {
          next();
        }
      });

      server.middlewares.use("/js/camera-card.js", async (_request, response, next) => {
        try {
          const jrtiResponse = await fetch(`${JRTI_TARGET}/js/camera-card.js`);

          if (!jrtiResponse.ok) {
            next();
            return;
          }

          response.setHeader("content-type", "application/javascript; charset=utf-8");
          response.end(patchJrtiCameraCard(await jrtiResponse.text()));
        } catch {
          next();
        }
      });
    },
  };
}
