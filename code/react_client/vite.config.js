import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /api to the FastAPI backend on PORT_BASE (8817), so
// the browser sees one origin and sends the HttpOnly session cookie normally.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8817",
    },
  },
});
