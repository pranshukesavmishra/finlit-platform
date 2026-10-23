import { defineConfig, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";

// One API for the browser, two backends behind it (mirrors deploy/Caddyfile on the VPS):
//   research service  -> /api/stocks/*, /api/screener/*, /api/results/*, /api/health, /api/auth/*, /api/me/*, /api/admin/*   (finlit-platform/backend)
//   site backend      -> everything else under /api, plus /api/stocks/admin/*   (Financial-Portfolio/backend)
const RESEARCH = process.env.RESEARCH_API || "http://127.0.0.1:8000";
const SITE = process.env.SITE_API || "http://127.0.0.1:8001";
const proxy: Record<string, ProxyOptions> = {
  "^/api/stocks/admin": { target: SITE, changeOrigin: true },
  "^/api/(stocks|screener|results|health|ping|auth|me|admin|ipos|feed|alerts|notifications|premium|notify|indices|compare|forum|graphs|advanced|etf|mf|dcf|search|logos|macro)": { target: RESEARCH, changeOrigin: true },
  "/api": { target: SITE, changeOrigin: true },
};

export default defineConfig({
  base: process.env.VITE_BASE || "/",
  plugins: [react()],
  server: { port: 5173, proxy },
  preview: { port: 4173, proxy },
  build: { target: "es2022", sourcemap: true, chunkSizeWarningLimit: 300 },
});
