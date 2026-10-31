import { defineConfig, type Plugin, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";
import { execSync } from "node:child_process";

// Build identity: APP_VERSION / GIT_COMMIT (set by the Docker build, which has no .git) -> git short sha -> timestamp.
// It is compiled into the bundle (__APP_VERSION__) and written to dist/version.json, which the server sends with no-cache.
// The running page compares the two (src/lib/version.ts) and offers a refresh when they differ.
const builtAt = new Date().toISOString();
const gitSha = () => { try { return execSync("git rev-parse --short=7 HEAD", { stdio: ["ignore", "pipe", "ignore"] }).toString().trim(); } catch { return ""; } };
const fromEnv = (process.env.APP_VERSION || process.env.GIT_COMMIT || "").trim().slice(0, 12);
const version = fromEnv && fromEnv !== "unknown" ? fromEnv : gitSha() || builtAt.replace(/\D/g, "").slice(0, 14);
const versionFile = (): Plugin => ({
  name: "finlit-version-json",
  generateBundle() { this.emitFile({ type: "asset", fileName: "version.json", source: JSON.stringify({ version, builtAt }) + "\n" }); },
});

// One API for the browser, two backends behind it (mirrors deploy/Caddyfile on the VPS):
//   research service  -> /api/stocks/*, /api/screener/*, /api/results/*, /api/health, /api/auth/*, /api/me/*, /api/admin/*   (finlit-platform/backend)
//   site backend      -> everything else under /api, plus /api/stocks/admin/*   (Financial-Portfolio/backend)
const RESEARCH = process.env.RESEARCH_API || "http://127.0.0.1:8000";
const SITE = process.env.SITE_API || "http://127.0.0.1:8001";
const proxy: Record<string, ProxyOptions> = {
  "^/api/stocks/admin": { target: SITE, changeOrigin: true },
  "^/api/(stocks|screener|results|health|ping|auth|me|admin|ipos|feed|alerts|notifications|premium|notify|indices|compare|forum|graphs|advanced|etf|mf|dcf|search|logos|client-errors|macro|markets|flows|options|commodity-prices|prism)": { target: RESEARCH, changeOrigin: true },
  "^/mcp$": { target: RESEARCH, changeOrigin: true, bypass: (req) => (req.method === "GET" && (req.headers.accept || "").includes("text/html") ? "/index.html" : undefined) },   // MCP endpoint for AI assistants; a browser opening /mcp gets the page
  "^/.well-known/mcp.json": { target: RESEARCH, changeOrigin: true },
  "/api": { target: SITE, changeOrigin: true },
};

export default defineConfig({
  base: process.env.VITE_BASE || "/",
  plugins: [react(), versionFile()],
  define: { __APP_VERSION__: JSON.stringify(version), __BUILT_AT__: JSON.stringify(builtAt) },
  server: { port: 5173, proxy },
  preview: { port: 4173, proxy },
  build: { target: "es2022", sourcemap: "hidden", chunkSizeWarningLimit: 300 },
});
