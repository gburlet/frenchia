import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const target = process.env.VITE_PROXY_TARGET ?? "http://localhost:8000";
const proxy = { target, changeOrigin: false };

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "src") },
  },
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    proxy: { "/api": proxy, "/admin": proxy, "/static": proxy },
    watch: process.env.VITE_USE_POLLING === "true" ? { usePolling: true } : undefined,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    // Generous: the suite shares the machine with the local LLM during content generation.
    testTimeout: 20000,
  },
});
