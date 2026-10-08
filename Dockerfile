# Production image for the Flask app + built React frontend.
# Built by pipelines/docker-compose.prod.yml; Caddy sits in front of it.

# --- frontend build ---------------------------------------------------------
FROM node:20-alpine AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build                      # -> /src/frontend/dist

# --- app --------------------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./
COPY src/ ./src/
COPY --from=frontend /src/frontend/dist ./frontend/dist

RUN useradd --create-home --uid 10001 web
USER web

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/db/stations', timeout=4)"

# One worker: the rate limiter keeps its counters in process memory.
CMD ["gunicorn", "--workers", "1", "--threads", "8", "--bind", "0.0.0.0:8000", \
     "--access-logfile", "-", "--forwarded-allow-ips", "*", "app:app"]
