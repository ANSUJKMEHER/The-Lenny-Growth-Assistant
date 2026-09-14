# Convenience targets for The Lenny Growth Assistant.
.DEFAULT_GOAL := help
PYTHON ?= python3
VENV := .venv

.PHONY: help setup up down logs test seed ingest run

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Create a virtualenv and install dependencies
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -r requirements.txt

up: ## Start the full stack (Postgres + API) with Docker Compose
	docker compose up --build -d

down: ## Stop the stack
	docker compose down

logs: ## Tail API logs
	docker compose logs -f api

seed: ## Ingest the bundled sample transcripts (needs a running API)
	curl -s -X POST http://localhost:8000/api/ingest/seed | jq .

ingest: ## Ingest transcripts from backend/data/transcripts (needs a running API)
	curl -s -X POST http://localhost:8000/api/ingest | jq .

run: ## Run the API locally (non-Docker) against the configured DATABASE_URL
	cd backend && ../$(VENV)/bin/uvicorn app.main:app --reload

test: ## Run the automated test suite
	$(VENV)/bin/pytest -q
