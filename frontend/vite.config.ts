import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendTarget = process.env.VITE_BACKEND_URL || "http://localhost:8000";
const port = Number(process.env.VITE_PORT || 5173);

// DevForge frontend dev server.
// All /api/* requests are proxied to the FastAPI backend, so the UI can use
// relative URLs and work from any preview host.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port,
    // allow the sandboxed preview host (any host in dev; restrict in prod)
    allowedHosts: true,
    proxy: {
      "/api": {
        target: backendTarget,
        changeOrigin: true,
      },
    },
  },
});
