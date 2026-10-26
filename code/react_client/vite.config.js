import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /api and /auth to the FastAPI backend on PORT_BASE
// (8817), so the browser sees one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8817",
      "/auth": "http://127.0.0.1:8817",
    },
  },
});
