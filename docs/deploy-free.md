# Free deployment

The step-by-step guide is [LAUNCH-GUIDE.md](LAUNCH-GUIDE.md) (PDF: `FinLit-Launch-Guide.pdf`). It covers Neon, MongoDB Atlas and Render,
every environment variable, first sign-ins, keep-awake, backups, the Gemini chat, email, the custom domain, troubleshooting and costs.

Files that implement it: `render.yaml`, `Dockerfile`, `deploy/render-start.sh`, `deploy/scheduler.sh`, `scripts/backup.sh`,
`.github/workflows/keepalive.yml`, `frontend/e2e/deploy_check.mjs` (run it against the live address after deploying).
