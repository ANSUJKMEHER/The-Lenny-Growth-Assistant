# Build log — coding-agent sessions

This is a condensed, honest log of how the system was built with AI assistance,
including the notable failed attempts and the corrections. Secrets/sensitive
details removed.

---

## Iteration 1 — Scoping & contracts first

**What:** after reading the assignment, the first move was *not* code — it was a
discovery brief (user/problem, success metric, assumptions, scope) that became
`PRD.md`. Then I fixed the API contracts (`schemas.py`) and data model (`models.py`)
before any behavior, so every layer had a stable target.

**Decision recorded:** use **JSONB embeddings + Python cosine** instead of pgvector,
and a **vanilla-JS frontend** (no build step). Both minimize evaluator friction.

## Iteration 2 — LLM abstraction

**Attempt:** started with a single `AnthropicProvider` hardcoded to the official SDK.

**Failure / correction:** the demo must run with **local Ollama and no API keys**, so
a single-provider design was wrong. Rebuilt as a provider-agnostic `LLMProvider`
interface with normalized `ChatMessage`/`ToolCall`/`LLMResponse` types and three
implementations (Ollama native `/api/chat`, Anthropic `/v1/messages`, OpenAI
`/chat/completions`) over `httpx` — no SDK dependency, transparent and testable.

## Iteration 3 — Retrieval fallback

**Attempt:** assumed Ollama's `nomic-embed-text` would always be available.

**Failure / correction:** a fresh evaluator might not have the embedding model pulled.
Added a deterministic **hashing bag-of-words lexical fallback** (`embedder.py`) so
ingestion and retrieval still work keyword-style with zero embeddings. Also added a
BM25 path in the retriever for corpora with no stored vectors.

## Iteration 4 — Sanitization config error

**Failure:** `nh3.clean(...)` raised
`ValueError: "rel" attribute is not allowed for tag "a" when link_rel is set`.

**Correction:** `rel` was both in the allowlist *and* managed by `link_rel`. Removed
`rel` from the attribute allowlist and let `link_rel="noopener noreferrer nofollow"`
own it. (This is now covered by `tests/test_security.py`.)

## Iteration 5 — Static path resolved relative to CWD

**Failure:** app import crashed with
`RuntimeError: Directory 'app/static' does not exist` when the process CWD wasn't
`backend/` (uvicorn from a different dir, and pytest from the repo root).

**Correction:** resolved `_STATIC_DIR` from `__file__` so the static mount and
`index.html` work regardless of CWD.

## Iteration 6 — Retrieval method label

**Failure:** a test asserted `method == "bm25"` when Ollama was unreachable, but
ingestion had stored lexical fallback *vectors*, so the retriever correctly took the
vector-similarity branch (labeled `"embedding"`).

**Correction:** the behavior was actually correct (relevant chunk returned). Relaxed
the assertion to `method in {"embedding","bm25"}` and documented that "embedding"
here may mean lexical-fallback vectors.

## Iteration 7 — Idempotent ingestion & citations

**Decision:** content-hash dedupe on `transcript_sources.content_hash` so re-running
ingestion never duplicates data. Citations are captured during retrieval and
persisted on the assistant message as JSON.

## Iteration 8 — Optional Claude Agent SDK integration

**Request:** wire in the official Anthropic Claude Agent SDK for the Anthropic path
(in addition to the built-in loop), and document the trade-off.

**Discovery:** inspecting `claude-agent-sdk` (v0.2.x) showed its transport spawns the
**Claude Code CLI** (`claude`) as a subprocess, and custom tools are exposed via an
in-process MCP server (`create_sdk_mcp_server` + `@tool`). So "use the SDK" has three
prerequisites: the Python package, the CLI binary, and an Anthropic key.

**Design:** added `ClaudeSDKAgent` (same `run(ctx, history)` interface) that exposes
the existing tools/skills to the SDK as an MCP server, and `select_agent()` that
picks the runtime via `AGENT_RUNTIME` (`auto`/`claude_sdk`/`builtin`). `auto` checks
`can_use_claude_sdk()` (importable + CLI on PATH) and falls back to the built-in loop
so the keyless Ollama demo is unaffected.

**Failure / correction:** an early test tried to monkeypatch `Settings.agent_runtime`
as a plain class attribute, which pydantic ignores. Corrected to monkeypatch the
module-level `get_settings` + availability probes directly (see `test_claude_sdk.py`).

**Result:** 29 tests pass; the Claude Agent SDK is genuinely usable on the Anthropic
path while the demo still runs keyless on Ollama.

## Iteration 9 — UI/UX overhaul + Ship 30 length enforcement

**What:** two reviewer-style gaps remained. (1) The frontend was functional but
visually flat. (2) The Ship 30 skill asked for ~1,250 words but had no length
guardrail, and local models under-generate badly (often stopping at a few hundred
words).

**Correction (UI):** rebuilt `index.html`/`styles.css`/`app.js` with a full design
system — CSS-variable light **and** dark themes (persisted, OS-preference default),
gradient brand, avatar-anchored message bubbles, a hero empty state with icon
suggestion cards, **expandable citations** (title always visible, excerpt revealed
on click), session delete, and copy actions on responses/artifacts. Kept the
vanilla-JS/no-build constraint and all accessibility affordances.

**Correction (Ship 30):** added a bounded word-count enforcement loop — if a draft
is under the floor (~1,000 words), the skill issues a single structured
"expand to ~1,250 words" continuation, capped at two rounds and never hard-failing
the skill if the provider can't cooperate. Covered by `test_ship30_skill_does_not_expand_long_essay`.

**Result:** 30 tests pass; UI verified in both themes (no console errors; graceful
`503` renders as a styled error bubble).

## Iteration 10 — Real grounding, deep citations, streaming, run.sh

**What:** a side-by-side review against a peer submission surfaced four concrete
gaps: (1) only 3 synthetic `[SAMPLE]` transcripts vs. real data, (2) citations
lacked guest/timestamp/source links, (3) no streaming (a big perceived-quality
loss on slow local models), and (4) no one-command bootstrap.

**Corrections:**
- **Real corpus** — added `core/rag/fetch.py`, which fetches the official
  `LennysNewsletter/lennys-newsletterpodcastdata` starter pack (50 real episodes)
  at runtime and ingests it (idempotent, raw files never committed). `ensure_corpus`
  runs on first boot, falling back to the bundled samples offline.
- **Speaker/timestamp chunking** — added `chunk_speaker_turns()` + `parse_speaker_turns()`
  so speaker-labelled transcripts are chunked with per-chunk `speaker` + `timestamp`
  metadata (new `Chunk` columns). Citations now carry guest + timestamp + source URL.
- **Streaming** — added a provider `stream()` contract (native for Ollama, single-shot
  fallback for others), an `Agent.run_stream()` event loop (`token`/`tool`/`done`),
  and `POST /api/sessions/{id}/messages/stream` (SSE). The frontend consumes SSE with
  a non-streaming fallback and shows progress statuses.
- **Bootstrap** — added `./run.sh` (starts Ollama, pulls models, boots via Docker
  Compose or local fallback).

**Failure / correction:** the first streaming refactor left a stray `_history_for`
stub and compared `ev.kind == AgentEvent` (class) instead of a string; caught by
inspection before running, rewrote `chat.py` cleanly with a shared `_prepare_turn` /
`_finalize_turn` split.

**Result:** 36 tests pass; verified live fetch (50 episodes → 4,622 chunks) and the
SSE endpoint's graceful 503 (no provider) path.

## Verification

- `pytest -q` → **36 passed** (retrieval, speaker-turn chunking, security,
  ingestion, agent + skills + length enforcement, API validation + graceful LLM
  failure + streaming endpoint, and agent-runtime selection).
- Smoke test: server boots, `/health` and `/health/ready` return correct status,
  frontend + static assets serve, all 11 API routes registered in OpenAPI.

## Known, deliberate trade-offs

- **No streaming (SSE)** — full-turn responses + typing indicator; streaming is an
  additive change (documented in PRD/architecture).
- **JSONB vs pgvector** — fine for demo-scale corpus; one-file swap to scale.
- **Two agent runtimes** (built-in loop + optional Claude Agent SDK) — a small amount
  of glue in exchange for satisfying both the "use the Claude Agent SDK" requirement
  and the "run keyless on Ollama" requirement.
- **Sample transcripts** — clearly-marked `[SAMPLE]` files so the demo runs offline;
  real Lenny transcripts must be ingested by the client (ingestion points at the
  public source).
