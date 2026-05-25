import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:5000",
        changeOrigin: true,
      },
      "/jrti": {
        target: "http://192.168.20.104:8080",
        changeOrigin: true,
        rewrite: path => path.replace(/^\/jrti/, ""),
      },
      "/camera": {
        target: "http://192.168.20.104:8080",
        changeOrigin: true,
      },
      "/cameras": {
        target: "http://192.168.20.104:8080",
        changeOrigin: true,
      },
      "/session": {
        target: "http://192.168.20.104:8080",
        changeOrigin: true,
      },
      "/viewer.html": {
        target: "http://192.168.20.104:8080",
        changeOrigin: true,
      },
      "/js": {
        target: "http://192.168.20.104:8080",
        changeOrigin: true,
      },
      "/css": {
        target: "http://192.168.20.104:8080",
        changeOrigin: true,
      },
      "/images": {
        target: "http://192.168.20.104:8080",
        changeOrigin: true,
      },
      "/recordings": {
        target: "http://192.168.20.104:8080",
        changeOrigin: true,
      },
    },
  },
});
