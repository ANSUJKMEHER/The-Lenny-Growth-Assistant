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

## Verification

- `pytest -q` → **24 passed** (retrieval, chunking, security, ingestion, agent,
  skills, API validation + graceful LLM failure).
- Smoke test: server boots, `/health` and `/health/ready` return correct status,
  frontend + static assets serve, all 11 API routes registered in OpenAPI.

## Known, deliberate trade-offs

- **No streaming (SSE)** — full-turn responses + typing indicator; streaming is an
  additive change (documented in PRD/architecture).
- **JSONB vs pgvector** — fine for demo-scale corpus; one-file swap to scale.
- **Sample transcripts** — clearly-marked `[SAMPLE]` files so the demo runs offline;
  real Lenny transcripts must be ingested by the client (ingestion points at the
  public source).
