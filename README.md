# The Lenny Growth Assistant

A full-stack, AI-powered conversational assistant grounded in **Lenny's Podcast**
transcripts. Users ask product & growth questions, get **cited, grounded answers**,
turn answers into **Ship 30 for 30–style essays**, and generate **Markdown / HTML
artifacts** that render inside the app — without ever touching prompts, models, or
infrastructure.

Built for the *Forward Deployed Engineer* take-home assignment. It is a small,
production-shaped deployment: FastAPI backend, an agent layer with a clean
tool-calling contract, RAG retrieval, PostgreSQL persistence, a swappable LLM
backend (local Ollama **or** Anthropic **or** OpenAI), and a Docker Compose
one-command startup.

---

## Table of contents

- [What it does](#what-it-does)
- [Architecture at a glance](#architecture-at-a-glance)
- [Quick start (Docker Compose)](#quick-start-docker-compose)
- [Quick start (local, no Docker)](#quick-start-local-no-docker)
- [Configuration](#configuration)
- [Model providers & toggling](#model-providers--toggling)
- [Ingesting transcripts](#ingesting-transcripts)
- [Running tests](#running-tests)
- [Project structure](#project-structure)
- [API reference](#api-reference)
- [Security model](#security-model)
- [Troubleshooting](#troubleshooting)
- [Extending the system](#extending-the-system)
- [Deliverables index](#deliverables-index)

---

## What it does

| Capability | Details |
|---|---|
| **Grounded chat** | RAG over **real Lenny's Podcast transcripts** (auto-fetched from the official public dataset on first boot). Answers cite the guest + episode + timestamp; the assistant admits when the corpus doesn't support an answer instead of hallucinating. |
| **Streaming** | Real Server-Sent Events (SSE) token streaming with progress statuses ("Searching transcripts…") and a non-streaming fallback. |
| **Sessions** | Independent chat sessions with full history persisted in PostgreSQL. |
| **Ship 30 for 30 skill** | A dedicated, encoded skill that turns grounded material into a ~1,250-word skimmable essay (hook, narrative arc, headings/bullets/bold, concrete takeaway) with length enforcement. |
| **Artifact generation** | Produce Markdown documents or complete HTML/CSS snippets, rendered in a side-by-side **Artifact Viewer** with copy / download / open-in-new-tab. |
| **Flexible LLM config** | Switch between Ollama (local, keyless — the demo default), Anthropic, and OpenAI from the UI or API. No code changes. |
| **Operability** | Structured logs, health/readiness endpoints, graceful degradation, `.env.example` with safe defaults, Docker Compose + `run.sh`. |

## Architecture at a glance

```
Browser (vanilla JS SPA)
   │  REST (JSON)
   ▼
FastAPI ──▶ API routers (sessions · chat · config · ingest · artifacts)
   │              │
   │              ▼
   │        Agent (tool-calling loop)
   │              ├── search_transcripts ──▶ Retriever (embedding or BM25) ──▶ PostgreSQL
   │              ├── write_ship30_essay ──▶ LLM (grounded) + artifact
   │              └── generate_artifact ──▶ LLM + sanitize + artifact
   │
   ├──▶ LLM layer (Ollama | Anthropic | OpenAI)  ← provider-agnostic interface
   └──▶ PostgreSQL (conversations, messages, artifacts, sources, chunks)
```

Full details, DB schema, endpoint contracts, and the agent-routing design are in
[docs/architecture.md](docs/architecture.md).

---

## Quick start

**One command (recommended):**

```bash
./run.sh
```

`run.sh` starts Ollama (pulling `llama3.1` + `nomic-embed-text` if needed), creates
`.env` from `.env.example`, and boots the stack with Docker Compose (or a local
fallback). On first boot the app also auto-fetches the **official Lenny's Podcast
starter dataset** (50 real episodes) so answers are grounded in real content.

### Quick start (Docker Compose)

Prerequisites: **Docker** + **Docker Compose**, and **Ollama** running on your host
with a model pulled (the demo requires local Ollama).

```bash
# 1. Install + start Ollama (https://ollama.com), then pull models:
ollama pull llama3.1              # chat model (or any model you prefer)
ollama pull nomic-embed-text      # embeddings for RAG

# 2. Clone and start the stack
git clone <your-repo-url> && cd lenny-growth-assistant
cp .env.example .env               # safe defaults; no secrets needed for Ollama
docker compose up --build -d

# 3. Open the app
open http://localhost:8000
```

The API **auto-fetches 50 real Lenny's Podcast transcripts** on first start (see
[Ingesting transcripts](#ingesting-transcripts)), so the demo works end-to-end
immediately with genuine grounding. If the network is unavailable, it falls back to
the bundled clearly-marked `[SAMPLE]` transcripts.

> **macOS / Windows note:** Docker can't reach `localhost` for Ollama directly.
> Set `OLLAMA_BASE_URL=http://host.docker.internal:11434` in `.env` (the Compose
> file already maps `host.docker.internal`). On Linux, `localhost` works as-is.

## Quick start (local, no Docker)

```bash
# 1. Python 3.11+
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. PostgreSQL (any install). Create the database:
createdb lenny

# 3. Configure
cp .env.example .env
#    DATABASE_URL=postgresql+asyncpg://<user>:<pass>@localhost:5432/lenny

# 4. Start Ollama + pull models (as above)

# 5. Run
cd backend
uvicorn app.main:app --reload
```

Open http://localhost:8000. `make run` is a convenience wrapper.

---

## Configuration

Every setting is an environment variable with a safe default — see
[`.env.example`](.env.example) for the full annotated list. The important ones:

| Variable | Default | Required? | Purpose |
|---|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://lenny:lenny@localhost:5432/lenny` | No | PostgreSQL connection string |
| `LLM_PROVIDER` | `ollama` | No | Default backend (`ollama` / `anthropic` / `openai`) |
| `AGENT_RUNTIME` | `auto` | No | Agent engine: `auto` / `claude_sdk` / `builtin` |
| `CLAUDE_CLI_PATH` | *(empty)* | Only for SDK | Path to the Claude Code CLI binary |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | No | Ollama endpoint |
| `OLLAMA_MODEL` | `llama3.1` | No | Local chat model |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | No | Embedding model |
| `ANTHROPIC_API_KEY` | *(empty)* | Only for Anthropic | Cloud API key |
| `OPENAI_API_KEY` | *(empty)* | Only for OpenAI | Cloud API key |
| `LLM_FALLBACK_ENABLED` | `true` | No | Auto-fallback between providers |
| `RETRIEVAL_TOP_K` | `6` | No | Chunks returned per search |

**Never commit secrets.** `.env` is git-ignored; `.env.example` contains no keys.

## Model providers & toggling

The active provider is **visible in the UI** (sidebar button + header badge) and
switchable at runtime:

- **UI** — click the provider button in the sidebar, choose a provider.
- **API** — `PUT /api/config` with `{"provider": "ollama"}`.

```bash
curl -X PUT http://localhost:8000/api/config \
  -H 'Content-Type: application/json' -d '{"provider":"anthropic"}'
```

**Fallback behavior** (`LLM_FALLBACK_ENABLED=true`): if the configured provider is
unconfigured or its healthcheck fails, the app tries `ollama → anthropic → openai`
and logs the fallback. If none work, the chat endpoint returns a structured `503`.

### Agent runtime (Claude Agent SDK)

Per the brief, the **agent layer** can run on the official **Anthropic Claude Agent
SDK**. It's wired in as an optional runtime (`AGENT_RUNTIME`):

- `auto` (default) — use the SDK when the Anthropic provider is active **and** the
  SDK + Claude Code CLI are installed; otherwise use the built-in loop.
- `claude_sdk` — require the SDK.
- `builtin` — always use the built-in provider-agnostic loop (used for the keyless
  Ollama demo).

To enable the SDK path:

```bash
pip install claude-agent-sdk   # or: pip install ".[anthropic-sdk]"
npm install -g @anthropic-ai/claude-code   # the CLI the SDK spawns
# then set ANTHROPIC_API_KEY and LLM_PROVIDER=anthropic
```

Both runtimes share the same tools/skills and citations, so behavior is consistent.
See [docs/architecture.md §5](docs/architecture.md) for the full trade-off.

---

## Ingesting transcripts

The knowledge base is **auto-populated on first boot** with the official Lenny's
Podcast starter dataset (50 real episodes; source:
[`LennysNewsletter/lennys-newsletterpodcastdata`](https://github.com/LennysNewsletter/lennys-newsletterpodcastdata),
used under its personal/non-commercial license). Transcripts are fetched at
runtime rather than committed, chunked (with speaker + timestamp preserved), and
indexed with source metadata.

```bash
# Fetch + ingest the official starter pack on demand:
curl -X POST http://localhost:8000/api/ingest/fetch

# Ingest bundled samples (offline fallback):
curl -X POST http://localhost:8000/api/ingest/seed

# Ingest every file in backend/data/transcripts:
curl -X POST http://localhost:8000/api/ingest

# Ingest a transcript from a URL:
curl -X POST http://localhost:8000/api/ingest/url \
  -H 'Content-Type: application/json' -d '{"url":"https://…"}'

# List indexed sources:
curl http://localhost:8000/api/sources
```

Answers are **traced back to their source** — citations include the episode
title, guest, timestamp, a source link, and the retrieved excerpt.

---

## Running tests

```bash
pip install -r requirements.txt
pytest -q            # or: make test
```

The suite runs against **SQLite** (no PostgreSQL/Ollama needed) and exercises the
critical paths: retrieval, chunking, sanitization, ingestion idempotency, agent
routing/skills, and the API (sessions, validation, graceful LLM failure). See
[docs/manual-test-plan.md](docs/manual-test-plan.md) for the UI test plan.

---

## Project structure

```
lenny-growth-assistant/
├── README.md                 # this file
├── PRD.md                    # product requirements & discovery brief
├── .env.example              # annotated configuration template
├── docker-compose.yml        # Postgres + API one-command stack
├── Dockerfile
├── Makefile
├── requirements.txt
├── pyproject.toml
├── docs/
│   ├── architecture.md       # schema, endpoints, flows, security, topology
│   ├── design.md             # UI/UX principles & decisions
│   ├── manual-test-plan.md   # UI test script
│   └── demo-video-script.md  # 2–3 min video outline
├── agent-transcripts/
│   └── build-log.md          # coding-agent logs incl. failed attempts & fixes
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI entrypoint, middleware, logging
│   │   ├── config.py         # typed settings from env
│   │   ├── db.py             # async engine/session, init
│   │   ├── models.py         # SQLAlchemy ORM models
│   │   ├── schemas.py        # Pydantic request/response contracts
│   │   ├── api/              # health, sessions, chat, config, ingest, artifacts
│   │   ├── core/
│   │   │   ├── llm/          # provider-agnostic LLM (ollama/anthropic/openai)
│   │   │   ├── agent/        # tool-calling loop + tools + skills
│   │   │   └── rag/          # chunker, embedder, retriever, ingest
│   │   └── static/           # SPA (index.html, styles.css, app.js, vendor libs)
│   └── data/transcripts/     # transcript files + README (SAMPLE data)
└── tests/                    # pytest suite
```

---

## API reference

Interactive docs are served at `/docs` (Swagger) and `/redoc`.

| Method & path | Purpose |
|---|---|
| `GET /health`, `GET /health/ready` | Liveness / readiness (DB + LLM) |
| `POST /api/sessions` | Create a chat session |
| `GET /api/sessions` | List sessions |
| `GET /api/sessions/{id}` | Session detail (messages + artifacts) |
| `DELETE /api/sessions/{id}` | Delete a session |
| `POST /api/sessions/{id}/messages` | Send a message → run the agent |
| `POST /api/sessions/{id}/messages/stream` | Same, but **SSE streaming** (`token`/`status`/`done`/`error` events) |
| `GET /api/config`, `PUT /api/config` | Read / switch model provider |
| `POST /api/ingest/fetch` | Fetch + ingest the official Lenny's Podcast dataset |
| `POST /api/ingest/seed` | Ingest bundled samples |
| `POST /api/ingest` | Ingest `data/transcripts/*` |
| `POST /api/ingest/url` | Ingest a transcript URL |
| `GET /api/sources` | List indexed transcript sources |
| `GET /api/artifacts/{id}` | Fetch an artifact |

Errors use a consistent envelope: `{"error": "...", "detail": "...", "code": "..."}`.
Invalid input returns `422`; missing resources `404`; LLM/provider failures `502`/`503`.

---

## Security model

- **Secrets** are never committed; keys are read from environment only.
- **Generated HTML is untrusted.** It is sanitized server-side with `nh3` (allowlist
  tags/attributes, safe URL schemes only, scripts/event-handlers stripped) **and**
  rendered client-side inside a `<iframe sandbox>` (no `allow-same-origin`, no
  `allow-scripts`) for defense in depth.
- **Markdown** is converted to HTML then passed through the same sanitizer.
- **Grounding** prevents fabrication: the agent is instructed to answer only from
  retrieved passages and to acknowledge unsupported questions.

See [docs/architecture.md § Security](docs/architecture.md) for what the viewer
permits, blocks, and why.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `503 No LLM provider available` | Ollama not running / model not pulled | `ollama serve`, then `ollama pull llama3.1` |
| Answers not grounded / "knowledge base doesn't cover it" | No transcripts ingested | `POST /api/ingest/seed` or `/api/ingest` |
| Embeddings slow or falling back to lexical | `nomic-embed-text` not pulled | `ollama pull nomic-embed-text` |
| `connection refused` on DB | Postgres not up | `docker compose up -d db`, check `DATABASE_URL` |
| Anthropic/OpenAI `401` | Key missing | Set the right API key in `.env` |
| Docker can't reach Ollama (macOS/Win) | Host networking | Set `OLLAMA_BASE_URL=http://host.docker.internal:11434` |

Diagnostics: `GET /health/ready` reports DB + LLM status; logs are structured
`key=value` lines (see `docker compose logs -f api`).

---

## Extending the system

- **Add a provider** — subclass `core/llm/base.py::LLMProvider`, register in
  `core/llm/factory.py::build_provider`.
- **Add a skill** — subclass `core/agent/tool.py::Tool` with a `name` /
  `description` / `parameters`, implement `run()`, and add it to
  `core/agent/agent.py::build_default_tools`. The router discovers it automatically.
- **Add transcript sources** — drop files in `backend/data/transcripts/` or extend
  `core/rag/ingest.py` with a new fetcher.

---

## Deliverables index

| # | Deliverable | Location |
|---|---|---|
| 1 | Public repository | *(this repo)* |
| 2 | README | `README.md` |
| 3 | PRD | `PRD.md` |
| 4 | Design | `docs/design.md` |
| 5 | Architecture | `docs/architecture.md` |
| 6 | Agent transcripts | `agent-transcripts/build-log.md` |
| 7 | Tests | `tests/` + `docs/manual-test-plan.md` |
| 8 | Demo video | `docs/demo-video-script.md` (script to record) |
