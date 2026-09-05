import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Inside Docker: BACKEND_URL=http://backend:8000 (service name, container port)
// Local dev outside Docker: fallback to http://localhost:8001 (host-mapped port)
const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8001";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      "/api": {
        target: backendUrl,
        changeOrigin: true,
      },
    },
  },
});
