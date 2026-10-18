# Build context: site-api/backend (the company's site backend, vendored into this repository).
#   docker build -f deploy/site-api/Dockerfile -t finlit-site-api site-api/backend   (run from the repository root)
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN useradd --create-home app && mkdir -p content_uploads portfolio_data && chown -R app /app
USER app
EXPOSE 8001
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2", "--no-server-header"]
