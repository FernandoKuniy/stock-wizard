import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// Component and unit tests for the frontend. jsdom gives the presentational components a DOM to
// render into; no backend, no network, no secrets, so it runs in CI as quickly as the linters.
// JSX is transformed by esbuild (automatic runtime), so no extra Vite plugin is needed.
export default defineConfig({
  resolve: {
    // Match the "@/..." path alias from tsconfig so imports resolve the same way as in the app.
    alias: { "@": fileURLToPath(new URL("./", import.meta.url)) },
  },
  esbuild: { jsx: "automatic" },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    css: false,
  },
});
