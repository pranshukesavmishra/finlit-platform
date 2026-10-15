FROM python:3.14-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY finlit ./finlit
COPY scripts ./scripts
# Fixtures let `FINEDGE_MODE=fixtures` run the whole stack offline.
COPY tests/fixtures ./tests/fixtures
RUN useradd --create-home finlit
USER finlit
EXPOSE 8000
CMD ["uvicorn", "finlit.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--loop", "uvloop", "--http", "httptools", "--no-access-log", "--no-server-header"]
