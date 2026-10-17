# One image = website + API, for the free single-service deployment (render.yaml). Build from the repository root.
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend ./
RUN VITE_BASE=/ npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/finlit ./finlit
COPY backend/scripts ./scripts
COPY backend/tests/fixtures ./tests/fixtures
COPY --from=web /web/dist ./web
COPY deploy/render-start.sh deploy/scheduler.sh ./
RUN mv render-start.sh start.sh && chmod +x start.sh scheduler.sh && useradd --create-home finlit && chown -R finlit /app
USER finlit
ENV FRONTEND_DIST=/app/web
EXPOSE 8000
CMD ["./start.sh"]
