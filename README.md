<div align="center">

# 🎙️ The Lenny Growth Assistant

**AI-powered answers grounded in real Lenny's Podcast episodes.**<br/>
Ask product & growth questions → get **cited, verifiable answers** → generate **essays & artifacts** — all from a single chat interface.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/React_18-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Ollama](https://img.shields.io/badge/Ollama-000000?style=for-the-badge&logo=ollama&logoColor=white)](https://ollama.com/)

<br/>

> *Built for the **Forward Deployed Engineer** take-home assignment.*<br/>
> *Production-shaped: FastAPI · Agent loop · RAG · PostgreSQL · Swappable LLM (Ollama / Anthropic / OpenAI) · Docker Compose one-command startup.*

</div>

---

## ✨ Features

<table>
<tr>
<td width="50%">

### 🔍 Grounded Chat
RAG over **real Lenny's Podcast transcripts** auto-fetched on first boot. Answers cite the **guest + episode + timestamp**. The assistant admits when the corpus doesn't cover a topic instead of hallucinating. A scope guard keeps it on-topic.

</td>
<td width="50%">

### ⚡ Real-Time Streaming
Server-Sent Events (SSE) with live token streaming and progress indicators (*"Searching transcripts…"*). Copy button on every response. Non-streaming fallback included.

</td>
</tr>
<tr>
<td width="50%">

### 📝 Ship 30 for 30 Skill
Turn grounded material into a **~1,250-word skimmable essay** — hook, narrative arc, headings, bullets, bold takeaways — with encoded writing principles and length enforcement.

</td>
<td width="50%">

### 🎨 Artifact Generation
Produce **Markdown documents** or complete **HTML/CSS snippets**, rendered in a side-by-side **Artifact Viewer** with copy · download · open-in-new-tab.

</td>
</tr>
<tr>
<td width="50%">

### 🔄 Flexible LLM Config
Switch between **Ollama** (local, keyless), **Anthropic**, and **OpenAI** from the UI or API — no code changes, no restarts. Auto-fallback between providers when one is unreachable.

</td>
<td width="50%">

### 🛡️ Production-Shaped
Structured logs · health/readiness probes · graceful degradation · sanitized HTML rendering (server-side `nh3` + client-side `<iframe sandbox>`) · `.env.example` with safe defaults · Docker Compose + `run.sh`.

</td>
</tr>
</table>

---

## 🏗️ Architecture

```
Browser (React 18 + TypeScript SPA)
   │  REST (JSON) + SSE
   ▼
FastAPI ──▶ API routers (sessions · chat · config · ingest · artifacts)
   │              │
   │              ▼
   │        Agent (tool-calling loop)
   │              ├── search_transcripts ──▶ Retriever (embedding + BM25) ──▶ PostgreSQL
   │              ├── write_ship30_essay ──▶ LLM (grounded) + artifact
   │              └── generate_artifact ──▶ LLM + sanitize + artifact
   │
   ├──▶ LLM layer (Ollama │ Anthropic │ OpenAI)  ← provider-agnostic interface
   └──▶ PostgreSQL (conversations, messages, artifacts, sources, chunks)
```

> 📖 Full details, DB schema, endpoint contracts, and agent-routing design in [**docs/architecture.md**](docs/architecture.md).

---

## 🚀 Quick Start

### One Command (Recommended)

```bash
./run.sh
```

> `run.sh` starts Ollama (pulling `qwen2.5:7b` + `nomic-embed-text` if needed), creates `.env` from `.env.example`, and boots the stack with Docker Compose. On first boot the app auto-fetches a **starter set of real Lenny's Podcast episodes** so answers are grounded in real content.

<details>
<summary><strong>🐳 Docker Compose (step-by-step)</strong></summary>

**Prerequisites:** Docker + Docker Compose, and **Ollama** running on your host.

```bash
# 1. Install + start Ollama (https://ollama.com), then pull models:
ollama pull qwen2.5:7b              # chat model (or any model you prefer)
ollama pull nomic-embed-text        # embeddings for RAG

# 2. Clone and start the stack
git clone <your-repo-url> && cd lenny-growth-assistant
cp .env.example .env               # safe defaults; no secrets needed for Ollama
docker compose up --build -d

# 3. Open the app
open http://localhost:8000
```

The API **auto-fetches real transcripts** on first start. If the network is unavailable, it falls back to the bundled `[SAMPLE]` transcripts.

> **macOS / Windows note:** Docker can't reach `localhost` for Ollama directly.
> Set `OLLAMA_BASE_URL=http://host.docker.internal:11434` in `.env` (the Compose
> file already maps `host.docker.internal`). On Linux, `localhost` works as-is.

</details>

<details>
<summary><strong>💻 Local (no Docker)</strong></summary>

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

</details>

---

## ⚙️ Configuration

Every setting is an environment variable with a safe default — see [`.env.example`](.env.example) for the full annotated list.

| Variable | Default | Required? | Purpose |
|:--|:--|:--:|:--|
| `DATABASE_URL` | `postgresql+asyncpg://lenny:lenny@localhost:5432/lenny` | — | PostgreSQL connection string |
| `LLM_PROVIDER` | `ollama` | — | Default backend (`ollama` / `anthropic` / `openai`) |
| `AGENT_RUNTIME` | `auto` | — | Agent engine: `auto` / `claude_sdk` / `builtin` |
| `CLAUDE_CLI_PATH` | *(empty)* | SDK only | Path to the Claude Code CLI binary |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | — | Ollama endpoint |
| `OLLAMA_MODEL` | `qwen2.5:7b` | — | Local chat model |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | — | Embedding model |
| `ANTHROPIC_API_KEY` | *(empty)* | Anthropic only | Cloud API key |
| `OPENAI_API_KEY` | *(empty)* | OpenAI only | Cloud API key |
| `LLM_FALLBACK_ENABLED` | `true` | — | Auto-fallback between providers |
| `RETRIEVAL_TOP_K` | `6` | — | Chunks returned per search |

> [!IMPORTANT]
> **Never commit secrets.** `.env` is git-ignored; `.env.example` contains no keys.

---

## 🔀 Model Providers & Toggling

The active provider is **visible in the UI** (sidebar button + header badge) and switchable at runtime:

- **UI** — click the provider button in the sidebar, choose a provider.
- **API** — `PUT /api/config` with `{"provider": "ollama"}`.

```bash
curl -X PUT http://localhost:8000/api/config \
  -H 'Content-Type: application/json' -d '{"provider":"anthropic"}'
```

**Fallback behavior** (`LLM_FALLBACK_ENABLED=true`): if the configured provider is unconfigured or its healthcheck fails, the app tries `ollama → anthropic → openai` and logs the fallback. If none work, the chat endpoint returns a structured `503`.

<details>
<summary><strong>🤖 Agent Runtime (Claude Agent SDK)</strong></summary>

Per the brief, the **agent layer** can run on the official **Anthropic Claude Agent SDK**. It's wired in as an optional runtime (`AGENT_RUNTIME`):

- `auto` (default) — use the SDK when the Anthropic provider is active **and** the SDK + Claude Code CLI are installed; otherwise use the built-in loop.
- `claude_sdk` — require the SDK.
- `builtin` — always use the built-in provider-agnostic loop (used for the keyless Ollama demo).

To enable the SDK path:

```bash
pip install claude-agent-sdk   # or: pip install ".[anthropic-sdk]"
npm install -g @anthropic-ai/claude-code   # the CLI the SDK spawns
# then set ANTHROPIC_API_KEY and LLM_PROVIDER=anthropic
```

Both runtimes share the same tools/skills and citations, so behavior is consistent. See [docs/architecture.md §5](docs/architecture.md) for the full trade-off.

</details>

---

## 📚 Ingesting Transcripts

The knowledge base is **auto-populated on first boot** with a starter set of the official Lenny's Podcast dataset (10 real episodes; the full archive — ~300 episodes — is available via `POST /api/ingest/fetch`). Source: [`ChatPRD/lennys-podcast-transcripts`](https://github.com/ChatPRD/lennys-podcast-transcripts), used under its personal/non-commercial license.

Transcripts are fetched at runtime rather than committed, chunked (with speaker + timestamp preserved), and indexed with source metadata.

```bash
# Fetch + ingest the official transcript archive on demand:
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

> Citations include the episode title, guest, timestamp, a source link, and the retrieved excerpt.

---

## 🧪 Running Tests

```bash
pip install -r requirements.txt
pytest -q            # or: make test
```

The suite runs against **SQLite** (no PostgreSQL/Ollama needed) and exercises the critical paths: retrieval, chunking, sanitization, ingestion idempotency, agent routing/skills, and the API (sessions, validation, graceful LLM failure).

> 📋 See [**docs/manual-test-plan.md**](docs/manual-test-plan.md) for the UI test plan.

---

## 📁 Project Structure

```
lenny-growth-assistant/
├── README.md                    ← you are here
├── PRD.md                       # product requirements & discovery brief
├── .env.example                 # annotated configuration template
├── docker-compose.yml           # Postgres + API one-command stack
├── Dockerfile
├── Makefile
├── requirements.txt
├── pyproject.toml
│
├── docs/
│   ├── architecture.md          # schema, endpoints, flows, security, topology
│   ├── design.md                # UI/UX principles & decisions
│   ├── manual-test-plan.md      # UI test script
│   └── demo-video-script.md     # 2–3 min video outline
│
├── agent-transcripts/
│   └── build-log.md             # coding-agent logs incl. failed attempts & fixes
│
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entrypoint, middleware, logging
│   │   ├── config.py            # typed settings from env
│   │   ├── db.py                # async engine/session, init
│   │   ├── models.py            # SQLAlchemy ORM models
│   │   ├── schemas.py           # Pydantic request/response contracts
│   │   ├── api/                 # health, sessions, chat, config, ingest, artifacts
│   │   ├── core/
│   │   │   ├── llm/             # provider-agnostic LLM (ollama/anthropic/openai)
│   │   │   ├── agent/           # tool-calling loop + tools + skills
│   │   │   └── rag/             # chunker, embedder, retriever, ingest
│   │   └── static/              # built React SPA (Vite output, served by FastAPI)
│   └── data/transcripts/        # transcript files + README (SAMPLE data)
│
├── frontend/                    # React + TypeScript + Vite source (build → static/)
└── tests/                       # pytest suite (56 backend + 6 frontend)
```

---

## 📡 API Reference

> Interactive docs are served at **`/docs`** (Swagger) and **`/redoc`**.

| Method & Path | Purpose |
|:--|:--|
| `GET /health` · `GET /health/ready` | Liveness / readiness (DB + LLM) |
| `POST /api/sessions` | Create a chat session |
| `GET /api/sessions` | List sessions |
| `GET /api/sessions/{id}` | Session detail (messages + artifacts) |
| `DELETE /api/sessions/{id}` | Delete a session |
| `POST /api/sessions/{id}/messages` | Send a message → run the agent |
| `POST /api/sessions/{id}/messages/stream` | Same, but **SSE streaming** (`token`/`status`/`done`/`error`) |
| `GET /api/config` · `PUT /api/config` | Read / switch model provider |
| `POST /api/ingest/fetch` | Fetch + ingest the official Lenny's Podcast dataset |
| `POST /api/ingest/seed` | Ingest bundled samples |
| `POST /api/ingest` | Ingest `data/transcripts/*` |
| `POST /api/ingest/url` | Ingest a transcript URL |
| `GET /api/sources` | List indexed transcript sources |
| `GET /api/artifacts/{id}` | Fetch an artifact |

**Error responses:** `422` (validation), `404` (not found), `502`/`503` (LLM/provider failure) — all use the `{"error": "...", "detail": ...}` envelope.

---

## 🔒 Security Model

| Layer | Protection |
|:--|:--|
| **Secrets** | Never committed; read from environment only. `.env` is git-ignored. |
| **Generated HTML** | Sanitized server-side with `nh3` (allowlist tags/attributes, safe URL schemes, scripts stripped) **and** rendered in `<iframe sandbox>` (no `allow-same-origin`, no `allow-scripts`) for defense in depth. |
| **Markdown** | Converted to HTML then passed through the same sanitizer. |
| **Grounding** | Agent instructed to answer only from retrieved passages; acknowledges unsupported questions. |

> 📖 See [**docs/architecture.md § Security**](docs/architecture.md) for what the viewer permits, blocks, and why.

---

## 🔧 Troubleshooting

| Symptom | Likely Cause | Fix |
|:--|:--|:--|
| `503 No LLM provider available` | Ollama not running / model not pulled | `ollama serve`, then `ollama pull qwen2.5:7b` |
| Answers not grounded | No transcripts ingested | `POST /api/ingest/seed` or `/api/ingest` |
| Embeddings slow / lexical fallback | `nomic-embed-text` not pulled | `ollama pull nomic-embed-text` |
| `connection refused` on DB | Postgres not up | `docker compose up -d db`, check `DATABASE_URL` |
| Anthropic/OpenAI `401` | Key missing | Set the right API key in `.env` |
| Docker can't reach Ollama | Host networking (macOS/Win) | Set `OLLAMA_BASE_URL=http://host.docker.internal:11434` |

> **Diagnostics:** `GET /health/ready` reports DB + LLM status; logs are structured `key=value` lines (`docker compose logs -f api`).

---

## 🧩 Extending the System

| What | How |
|:--|:--|
| **Add a provider** | Subclass `core/llm/base.py::LLMProvider`, register in `core/llm/factory.py::build_provider`. |
| **Add a skill** | Subclass `core/agent/tool.py::Tool` with `name` / `description` / `parameters`, implement `run()`, add to `core/agent/agent.py::build_default_tools`. Auto-discovered. |
| **Add transcript sources** | Drop files in `backend/data/transcripts/` or extend `core/rag/ingest.py` with a new fetcher. |

---

## 📦 Deliverables Index

| # | Deliverable | Location | Status |
|:--:|:--|:--|:--:|
| 1 | Public repository | *(this repo)* | ✅ |
| 2 | README | `README.md` | ✅ |
| 3 | PRD | `PRD.md` | ✅ |
| 4 | Design | `docs/design.md` | ✅ |
| 5 | Architecture | `docs/architecture.md` | ✅ |
| 6 | Agent transcripts | `agent-transcripts/build-log.md` | ✅ |
| 7 | Tests | `tests/` + `docs/manual-test-plan.md` | ✅ |
| 8 | Demo video | `docs/demo-video-script.md` *(script)* | 🎬 |

---

<div align="center">

**Built with ❤️ for the Forward Deployed Engineer take-home.**

*[Architecture](docs/architecture.md) · [Design](docs/design.md) · [PRD](PRD.md) · [Manual Tests](docs/manual-test-plan.md) · [Demo Script](docs/demo-video-script.md)*

</div>
