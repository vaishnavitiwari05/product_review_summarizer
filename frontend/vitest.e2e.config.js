// Live end-to-end tests: they talk to a REAL running backend (see ../scripts/e2e.sh).
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/__tests__/setup.js",
    include: ["src/e2e/**/*.test.{js,jsx}"],
    fileParallelism: false,             // files share one server + database
    testTimeout: 60000,
    css: false,
    env: { VITE_API_URL: process.env.E2E_API_URL || "http://127.0.0.1:8765" },
  },
});
