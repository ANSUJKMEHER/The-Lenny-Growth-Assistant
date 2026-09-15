# Multi-stage build: compile React frontend, then run FastAPI backend.
FROM node:20-alpine AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

# System deps: build tools for asyncpg/nh3 wheels, curl for healthchecks.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code and compiled React static assets.
COPY pyproject.toml ./
COPY backend/ ./backend/
COPY --from=frontend-builder /build/backend/app/static ./backend/app/static
COPY tests/ ./tests/

# The app is served from backend/; expose the FastAPI port.
WORKDIR /app/backend
EXPOSE 8000

# Healthcheck hits the liveness endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
