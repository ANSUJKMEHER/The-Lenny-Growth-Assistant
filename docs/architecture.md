# Architecture — The Lenny Growth Assistant

This document describes the system end-to-end so another engineer can operate and
extend it: data model, API contracts, component boundaries, ingestion/retrieval
flow, agent routing, model toggling, security, and deployment topology.

---

## 1. Component boundaries

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (backend/app/static) — vanilla JS SPA, no build step   │
│  chat · session list · provider switcher · artifact viewer       │
└───────────────────────────────┬─────────────────────────────────┘
                                │ JSON over REST
┌───────────────────────────────▼─────────────────────────────────┐
│  FastAPI (backend/app)                                           │
│  api/     → routers: health, sessions, chat, config, ingest,     │
│             artifacts                                            │
│  core/agent/ → Agent loop, Tool/Skill base, tools, skills        │
│  core/rag/   → chunker, embedder, retriever, ingest              │
│  core/llm/   → provider interface + ollama/anthropic/openai      │
│  db.py, models.py, schemas.py, config.py, security.py            │
└───────────────┬──────────────────────────────┬──────────────────┘
                │ asyncpg (SQLAlchemy async)    │ httpx
                ▼                              ▼
          PostgreSQL                    LLM providers (Ollama local,
                                        Anthropic/OpenAI cloud)
```

Key boundaries:
- **`core/llm`** is the *only* place that knows about a specific provider. The
  agent and skills depend only on the `LLMProvider` interface.
- **`core/agent`** owns routing and tool execution; it has no HTTP or DB concerns
  beyond the `ToolContext` handed to it.
- **`core/rag`** owns the knowledge base; the agent consumes it only through the
  retrieval tool.
- **`api`** owns HTTP concerns: validation, status codes, error envelopes.

## 2. Database schema (PostgreSQL)

| Table | Columns (key) | Purpose |
|---|---|---|
| `conversations` | `id` (PK), `title`, `user_id`, `created_at`, `updated_at` | one chat session |
| `messages` | `id` (PK), `conversation_id` (FK), `role`, `content`, `citations` (JSONB), `created_at` | user/assistant turns |
| `artifacts` | `id` (PK), `conversation_id` (FK), `message_id` (FK, nullable), `kind`, `title`, `content`, `created_at` | generated Markdown/HTML |
| `transcript_sources` | `id` (PK), `episode_id`, `title`, `speaker`, `url`, `published_at`, `content_hash` (unique) | an ingested transcript |
| `chunks` | `id` (PK), `source_id` (FK), `index`, `text`, `embedding` (JSONB), `token_count` | retrievable chunk |
| `app_settings` | `key` (PK), `value`, `updated_at` | runtime config (provider/model) |

Relationships: `conversation 1─N message 1─N artifact`; `transcript_source 1─N chunk`.
Deletes cascade (`conversation` → messages → artifacts; `source` → chunks).

**Why embeddings live as JSONB instead of pgvector:** the demo corpus is a few
hundred chunks; storing vectors as JSON and computing cosine in Python keeps the
Docker image small (no pgvector extension) and makes the stack trivially portable.
If the corpus grew, swapping to pgvector is a drop-in change inside `retriever.py`.

## 3. API contracts

All responses are JSON; errors use one envelope. See `schemas.py` for the exact
Pydantic shapes and `/docs` for the live OpenAPI spec.

```
POST /api/sessions {title?, user_id?}            → 201 ConversationOut
GET  /api/sessions                               → {sessions: [Summary]}
GET  /api/sessions/{id}                          → ConversationOut (messages + artifacts)
DEL  /api/sessions/{id}                          → 204
POST /api/sessions/{id}/messages {content}       → ChatResponse
GET  /api/config                                 → ConfigOut
PUT  /api/config {provider, model?}              → ConfigOut
POST /api/ingest/seed | /api/ingest | /api/ingest/url → IngestResult
GET  /api/sources                                → [SourceOut]
GET  /api/artifacts/{id}                         → ArtifactOut
GET  /health · /health/ready                     → status + checks
```

`ChatResponse`:

```json
{
  "message": {"id", "role", "content", "citations": [{"source_id","title","chunk_index","excerpt"}], "created_at"},
  "artifacts": [{"id","kind","title","content","created_at"}],
  "provider": "ollama",
  "model": "llama3.1",
  "grounded": true
}
```

`grounded` is `true` when the run used `search_transcripts` — a first-class signal
for the "≥80% grounded" success metric.

## 4. Ingestion & retrieval flow

```
transcript file/URL
   → parse frontmatter (title, episode_id, speaker, url)
   → sha256(content) → dedupe by content_hash (idempotent)
   → chunk_text()  (~400 tokens, 80 overlap, sentence sliding window)
   → embed each chunk  (Ollama nomic-embed-text, else lexical hashing fallback)
   → persist source + chunks
```

**Retrieval** (`Retriever.retrieve`):
1. Load all chunks + source metadata.
2. If any chunk has an embedding → embed the query → cosine similarity → top-k.
3. Else → BM25 over tokenized chunk text → top-k.
4. Empty result → return `[]`; the search tool then tells the agent to acknowledge.

**Traceability:** every retrieved chunk carries `source_id`, `title`, `episode_id`,
and `chunk_index`; these become the message's `citations`.

**Refresh:** re-running ingestion is safe (hash-deduplicated); new files add, edited
files create new sources (the old hash differs). A full "delete-and-reload" of a
single source is a one-line extension.

## 5. Agent routing

The brief names the **Anthropic Claude Agent SDK** and **Pi Coding Agent** as the
agent-layer runtime. We support **both** the official SDK *and* a built-in loop,
selected at runtime by `AGENT_RUNTIME`:

| `AGENT_RUNTIME` | Behavior |
|---|---|
| `auto` (default) | Use the **Claude Agent SDK** when the Anthropic provider is active *and* the SDK + Claude Code CLI are installed; otherwise use the built-in loop. |
| `claude_sdk` | Require the Claude Agent SDK (error if the package or CLI is missing). |
| `builtin` | Always use the built-in provider-agnostic loop. |

### 5.1 Built-in loop (works with every provider)

A bounded tool-calling loop (`MAX_ITERATIONS = 8`):

```
system prompt + history + tool schemas
   → LLM
   → if tool_calls: execute each, append results, loop
   → else: final answer
```

This is the runtime used for the **local Ollama demo** and any provider without the
SDK. It implements the same turn-based tool-use contract as the Claude Agent SDK
(tool schemas in → model requests calls → agent executes them → feeds results back),
but against our provider-agnostic LLM layer.

### 5.2 Claude Agent SDK (Anthropic path, optional)

`core/agent/claude_sdk_agent.py::ClaudeSDKAgent` drives the official
`claude-agent-sdk`. Our tools/skills are exposed to the SDK as an **in-process MCP
server** (`create_sdk_mcp_server`), so the SDK's model performs the same routing as
the built-in loop. Configuration: `allowed_tools=[]` (no filesystem/shell tools),
`permission_mode="bypassPermissions"` (our tools are in-process and safe, and a web
request can't answer interactive prompts), `setting_sources=[]` (deterministic — no
local `~/.claude` config).

**Prerequisites** (why this is optional, not default): the SDK spawns the **Claude
Code CLI** (`claude`) as its transport, so it needs `pip install claude-agent-sdk`
*and* the CLI binary, plus an Anthropic API key. That is more setup than the keyless
Ollama demo requires, so we gate it behind availability checks and fall back cleanly
(`claude_sdk_agent.can_use_claude_sdk()`).

### 5.3 Why not Pi Coding Agent?

Pi Coding Agent is an excellent local-first *coding* agent, but its loop is a
standalone CLI/UI oriented around editing a codebase, not an embeddable web-assistant
request path. The two runtimes above give the evaluator the requested SDK *and* the
keyless-local path without forcing an awkward CLI embedding.

### 5.4 The trade-off, stated plainly

We accept a small amount of glue code (two runtimes behind one `run(ctx, history)`
interface) in exchange for satisfying **both** hard constraints: the official
Claude Agent SDK is genuinely wired in for the Anthropic path, **and** the demo runs
identically on local Ollama with no keys. The two share `ToolContext`, tools, skills,
and citations, so behavior is consistent regardless of runtime.

### 5.5 Tools/skills (same across both runtimes)

Each exposes a JSON-schema function definition:

| Tool | Routing intent | Effect |
|---|---|---|
| `search_transcripts` | any substantive product/growth question | retrieves + records citations |
| `list_sources` | "what's in the KB?" | lists indexed episodes |
| `write_ship30_essay` | Ship 30 / polished written piece | grounded essay + markdown artifact |
| `generate_artifact` | "make me a doc/HTML/checklist" | grounded doc/HTML + artifact |

The **Ship 30 skill** is a *skill*, not a raw prompt: it encodes the writing
principles (hook, one big idea, 3-point narrative, skimmable formatting, specificity,
takeaway, ~1,250 words) as a system prompt constant and always grounds itself in
retrieved passages before composing.

**Tool failures are contained** — a failing tool returns an error string to the
model rather than crashing the loop.

## 6. Model toggling & fallback

- `LLM_PROVIDER` sets the startup default; `PUT /api/config` writes an override to
  `app_settings` (survives restart, no code change).
- `resolve_provider()` builds the requested provider, runs a healthcheck, and —
  if `LLM_FALLBACK_ENABLED` — falls back `ollama → anthropic → openai`.
- The active provider/model are surfaced in `GET /api/config`, the readiness
  endpoint, and the UI badge.
- Providers implement a common `complete(messages, tools)` contract; message/tool
  shapes are normalized in `core/llm/*`.

## 7. Security

- **Secrets:** env-only, `.env` git-ignored, `.env.example` has no keys.
- **Untrusted HTML artifacts:** two layers —
  1. **Server** (`core/security.py`): `nh3` allowlist sanitization — a fixed set of
     structural tags/attributes, safe URL schemes only (`http/https/mailto`), no
     `<script>`, no `on*` handlers, comments stripped, `rel=noopener noreferrer nofollow`.
  2. **Client** (`app.js`): HTML artifacts render inside `<iframe sandbox="">` (no
     `allow-same-origin`, no `allow-scripts`), `referrerpolicy=no-referrer`, so even
     if sanitization were bypassed the artifact cannot touch the app origin.
- **Markdown** is rendered server-side to HTML and passed through the same sanitizer;
  the client additionally runs DOMPurify before injecting chat markdown.
- **What the viewer permits/blocks:** permits text, links (http/https/mailto),
  images (http/https), tables, lists; blocks scripts, event handlers, iframes,
  forms, object/embed, `javascript:`/`data:` URLs, and same-origin access.

## 8. Observability & resilience

- **Logs:** single-line `key=value` structured lines (`level`, `logger`, request
  method/path/status/duration, startup/seed, fallback events, tool failures).
- **Health:** `/health` (liveness) and `/health/ready` (DB + LLM status with reasons).
- **Resilience:**
  - Missing keys → provider marked unavailable; fallback or `503`.
  - Ollama down → healthcheck fails → fallback or `503`; embedding falls back to lexical.
  - Model timeout → `ProviderError` → `502` with message.
  - Empty retrieval → explicit "not covered" + `grounded:false`.
  - DB down → `pool_pre_ping` + readiness reports it; requests return `500` envelope.

## 9. Deployment topology

```
[ host machine ]                 [ Docker network ]
 Ollama (11434)  ◄────────────── api (FastAPI :8000)
                                    │
                                    ▼
                                db (Postgres 16 :5432)  ── volume pgdata
```

- `docker-compose.yml` runs `db` + `api`; `api` reaches Ollama on the host via
  `host.docker.internal` (auto-mapped with `host-gateway` on Linux).
- `db` is health-checked; `api` waits for it. Static assets are baked into the image.
- Non-Docker runs replace `db` with any PostgreSQL reachable via `DATABASE_URL`.

## 10. Extension points

- New provider → subclass `LLMProvider`, register in `factory.build_provider`.
- New skill/tool → subclass `Tool`, add to `build_default_tools`.
- New transcript fetcher → extend `core/rag/ingest.py`.
- Streaming → add an SSE path that yields agent `complete()` deltas (providers
  already return full responses; streaming is an additive change).
- pgvector → replace JSONB cosine with `ORDER BY embedding <-> :q` in `retriever`.
