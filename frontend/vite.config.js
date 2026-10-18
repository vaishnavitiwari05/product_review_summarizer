import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Backend routes that the dev server forwards when VITE_API_URL is empty (same-origin mode).
const API_PATHS = ["/health", "/products", "/upload", "/sample", "/analyze", "/results"];
const target = process.env.VITE_PROXY_TARGET || "http://localhost:8000";
const proxy = Object.fromEntries(API_PATHS.map((p) => [p, { target, changeOrigin: true }]));

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy },
  preview: { port: 4173, proxy },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/__tests__/setup.js",
    css: false,
    exclude: ["**/node_modules/**", "src/e2e/**"],
  },
});
