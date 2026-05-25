import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const JRTI_TARGET = "http://192.168.20.104:8080";
const JRTI_SNAPSHOT_REFRESH_MS = 500;
const API_TARGET = globalThis.process?.env?.KSP_API_TARGET || "http://127.0.0.1:5002";

export default defineConfig({
  plugins: [react(), jrtiProxyOverride()],
  server: {
    host: "0.0.0.0",
    proxy: {
      "/api": {
        target: API_TARGET,
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

function patchJrtiDashboard(source) {
  return source
    .replace(/<title>Just Read The Instructions<\/title>/g, "<title>Camera Feeds</title>")
    .replace(
      "</head>",
      `  <style>
    html {
      scrollbar-color: rgba(148, 162, 181, 0.48) transparent;
      scrollbar-width: thin;
    }

    body {
      margin: 0 !important;
      padding: 0 !important;
      background: #0f151b !important;
      overflow: auto !important;
    }

    *::-webkit-scrollbar {
      width: 5px;
      height: 5px;
    }

    *::-webkit-scrollbar-track {
      background: transparent;
    }

    *::-webkit-scrollbar-thumb {
      border-radius: 999px;
      background: rgba(148, 162, 181, 0.36);
    }

    *::-webkit-scrollbar-thumb:hover {
      background: rgba(185, 196, 210, 0.62);
    }

    header,
    nav,
    footer,
    #controls,
    #settings,
    #error,
    #empty,
    [data-section="settings"] {
      display: none !important;
    }

    main,
    #app,
    #root {
      margin: 0 !important;
      padding: 0 !important;
      max-width: none !important;
      background: transparent !important;
    }

    #cameras-live {
      display: grid !important;
      grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr)) !important;
      gap: 0.9rem !important;
      margin: 0 !important;
      padding: 0.65rem !important;
    }

    .camera-card,
    camera-card {
      border-radius: 8px !important;
      border-color: rgba(148, 162, 181, 0.22) !important;
      background: #111820 !important;
      min-height: 17rem !important;
    }

    .camera-card video,
    .camera-card img,
    camera-card video,
    camera-card img {
      border-radius: 6px !important;
      min-height: 10rem !important;
      object-fit: cover !important;
    }

    @media (min-width: 1100px) {
      #cameras-live {
        grid-template-columns: repeat(auto-fit, minmax(20rem, 1fr)) !important;
      }

      .camera-card,
      camera-card {
        min-height: 18.5rem !important;
      }

      .camera-card video,
      .camera-card img,
      camera-card video,
      camera-card img {
        min-height: 11.5rem !important;
      }
    }
  </style>
</head>`,
    )
    .replace(/<h1>Just Read The Instructions<\/h1>/g, "<h1 hidden></h1>");
}

function jrtiProxyOverride() {
  return {
    name: "jrti-proxy-override",
    configureServer(server) {
      server.middlewares.use("/jrti/", async (request, response, next) => {
        if (request.url && !["/", ""].includes(request.url.split("?")[0])) {
          next();
          return;
        }

        try {
          const jrtiResponse = await fetch(`${JRTI_TARGET}/`);

          if (!jrtiResponse.ok) {
            next();
            return;
          }

          response.setHeader("content-type", "text/html; charset=utf-8");
          response.setHeader("cache-control", "no-store");
          response.end(patchJrtiDashboard(await jrtiResponse.text()));
        } catch {
          next();
        }
      });

      server.middlewares.use("/js/config.js", async (_request, response, next) => {
        try {
          const jrtiResponse = await fetch(`${JRTI_TARGET}/js/config.js`);

          if (!jrtiResponse.ok) {
            next();
            return;
          }

          response.setHeader("content-type", "application/javascript; charset=utf-8");
          response.setHeader("cache-control", "no-store");
          response.end(patchJrtiConfig(await jrtiResponse.text()));
        } catch {
          next();
        }
      });

    },
  };
}
