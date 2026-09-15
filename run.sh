#!/usr/bin/env bash
# The Lenny Growth Assistant — one-command startup.
#
# What this does:
#   1. Ensures Ollama is running and pulls the demo models (local demo is mandatory).
#   2. Creates .env from .env.example if missing (safe defaults, no secrets).
#   3. Boots the stack via Docker Compose, or falls back to a local run.
#
# Usage: ./run.sh
set -euo pipefail

say() { printf '\033[36m→\033[0m %s\n' "$1"; }
warn() { printf '\033[33m⚠\033[0m %s\n' "$1"; }

say "The Lenny Growth Assistant"

# 1. Ollama (local model — mandatory for the demo)
if command -v ollama >/dev/null 2>&1; then
  if ! curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
    say "Starting Ollama…"
    (ollama serve >/dev/null 2>&1 &) || true
    sleep 3
  fi
  say "Ensuring models are pulled (qwen2.5:7b, nomic-embed-text)…"
  ollama pull qwen2.5:7b || warn "could not pull qwen2.5:7b (a running Ollama is required for chat)"
  ollama pull nomic-embed-text || warn "could not pull nomic-embed-text (will fall back to lexical retrieval)"
else
  warn "Ollama not found — install it from https://ollama.com (the local demo needs it)."
fi

# 2. Configuration
if [ ! -f .env ]; then
  say "Creating .env from .env.example…"
  cp .env.example .env
fi

# 3. Launch
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  say "Starting the stack with Docker Compose (Postgres + API)…"
  docker compose up --build
else
  say "Docker not found — running locally (requires Python 3.11+ and PostgreSQL)."
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
  cd backend
  exec ../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
fi
