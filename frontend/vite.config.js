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
    },
  };
}
