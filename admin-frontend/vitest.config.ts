import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // Full-screen tests drive many user events; 5 s (the default) times out
    // on a loaded dev machine or CI runner without anything being wrong.
    testTimeout: 20000,
  },
});
