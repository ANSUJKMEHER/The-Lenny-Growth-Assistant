# PRD — The Lenny Growth Assistant

*Forward Deployed Engineer take-home · product requirements document*

---

## 1. Forward Deployment Brief (discovery)

### 1.1 User & problem

**Primary user:** a product manager or growth lead on a small product team who
already consumes Lenny's Podcast but struggles to *retrieve and reuse* what they
heard. They remember a concept ("that episode about activation"), not the
episode, the exact numbers, or the caveats.

**Job to be done:** turn the *tacit* knowledge scattered across dozens of hour-long
podcast transcripts into *reusable, citable* answers and written content — on
demand, without learning prompts, models, or infrastructure.

**Pain removed:**
1. **Recall cost** — no more scrubbing 60-minute episodes to find one framework.
2. **Hallucination risk** — answers are grounded in real transcripts and cite their source, so the team can trust (and verify) them.
3. **Rewrite cost** — turning a concept into a shareable essay or a checklist is manual today; the assistant does it in one step.
4. **Tool friction** — non-technical users get a chat UI, not a terminal or a prompt box.

### 1.2 Success metric

**Primary (product):** ≥ **80% of substantive answers are *grounded*** (produced via
the retrieval tool with at least one citation), measured per assistant message —
because the whole value proposition rests on trust.

**Secondary (operational):**
- **Time-to-answer** p95 < 30s with the local Ollama model (a usable chat feel).
- **Answer-abandonment:** the assistant explicitly *acknowledges* an unsupported
  question rather than answering when retrieval returns nothing (target: 100% of
  empty-retrieval turns acknowledge instead of guessing).

### 1.3 Assumptions (client brief was incomplete)

1. **No production deployment target given** → we deliver a Docker Compose stack that runs locally; the API is stateless and portable to any Postgres host (Railway/Supabase).
2. **Evaluator has no cloud API keys** → the *default* and *mandatory demo* path is local Ollama; cloud providers are optional and keyless-by-default.
3. **Transcript corpus is not shipped** → we bundle clearly-marked `[SAMPLE]` transcripts so the demo runs end-to-end, and provide ingestion that points at the real public transcript source. Real transcripts must be ingested by the client.
4. **"Session context" means per-session isolation** → each chat is independent; there is no cross-session user identity/memory (no auth requirement in the brief).
5. **~1,250-word Ship 30 essays** are a *long-form* adaptation of the classic ~250-word atomic essay; we keep the same principles, longer format (per the brief's explicit word count).
6. **Artifact rendering** must be safe → generated HTML is treated as untrusted and isolated (see §6).
7. **Single-tenant, small team** → no multi-tenancy, RBAC, or rate limiting beyond basic sanity.

### 1.4 Scope choices

**Included:**
- FastAPI backend with typed contracts, validation, structured errors, health/readiness.
- Provider-agnostic LLM layer: Ollama (default), Anthropic, OpenAI; runtime toggle + fallback.
- Agent loop with tool-calling and four capabilities: `search_transcripts`, `list_sources`, `write_ship30_essay`, `generate_artifact`.
- RAG: chunking, embedding (Ollama + lexical fallback), retrieval (vector + BM25), source citations.
- PostgreSQL persistence: conversations, messages, artifacts, sources, chunks, runtime settings.
- Ship 30 for 30 skill with **encoded** writing principles.
- Artifact Viewer (side-by-side), Markdown + HTML rendering, sandboxed isolation.
- SSE token streaming with progress statuses (`status`/`token`/`done`/`error` events) and a non-streaming fallback.
- Docker Compose one-command startup, `.env.example`, structured logging, graceful failure.
- Tests (API, retrieval, ingestion, security, agent) + manual UI test plan.

**Excluded (deliberately):**
- **Auth / multi-user accounts** — out of scope for a take-home; sessions are the isolation boundary.
- **Cloud vector DB (pgvector/Pinecone)** — the corpus is small; embeddings are stored as JSON arrays and similarity is computed in Python, keeping Docker minimal and the stack portable.
- **Fine-tuned re-ranking** — BM25 + cosine is sufficient for the demo corpus size.
- **Auth-gated artifact sharing** — artifacts are per-session, local to the app.

### 1.5 Risks & trade-offs

| Risk | Impact | Mitigation |
|---|---|---|
| **Hallucination** | Wrong answers erode trust | System prompt mandates "answer only from retrieved passages"; citations required; empty-retrieval → explicit acknowledgement. |
| **Local-model quality** | Ollama answers less precise than Claude | Grounding limits the surface (models summarize retrieved text); fallback to cloud available; temperature 0.2. |
| **Latency** | Long agent turns feel slow | Single-turn tool loop (≤8 steps), typed indicator, retrieval limited to top-k chunks. |
| **Cost** | Cloud usage bills | Local Ollama is the default; embeddings run locally; no auto-scaling. |
| **Data leakage** | Transcripts are (in reality) public podcast content, but the system may hold private context | No external calls beyond the configured LLM provider; secrets env-only; HTML artifacts can't reach the parent origin (sandboxed iframe). |
| **Unsafe artifact rendering** | XSS via generated HTML | Server-side `nh3` sanitization + client sandboxed iframe (defense in depth). |
| **Empty retrieval** | Silently empty answers | Explicit "not covered" message + `grounded:false` flag on the response. |
| **Ollama unavailable** | Demo fails | Fallback chain + `503` structured errors + readiness endpoint surfaces the cause. |

---

## 2. Requirements

### 2.1 Functional

- **F1** Start/switch/delete independent chat sessions.
- **F2** Ask product/growth questions; get grounded, cited answers with follow-up context.
- **F3** Acknowledge when the corpus does not support an answer.
- **F4** Generate a Ship 30 for 30 essay (~1,250 words) grounded in the corpus.
- **F5** Generate Markdown or HTML artifacts rendered in the in-app viewer.
- **F6** Switch model provider (Ollama/Anthropic/OpenAI) at runtime; see the active provider in the UI.
- **F7** Ingest transcripts from local files or URLs; idempotent re-ingestion.
- **F8** Persist everything to PostgreSQL.

### 2.2 Non-functional

- **N1** One-command reproducible startup (Docker Compose).
- **N2** Structured logs; health/readiness endpoints; graceful failure for missing keys, unreachable Ollama, timeouts, empty retrieval, DB down.
- **N3** Security: no committed secrets; untrusted HTML isolated.
- **N4** Accessibility + responsive UI.
- **N5** Meaningful automated tests.

---

## 3. Key user flows

1. **Ask & ground:** open app → new chat → "What does Lenny say about activation?" → agent searches transcripts → returns cited answer.
2. **Ship 30:** → "Write a Ship 30 essay on activation" → skill retrieves, composes ~1,250 words → artifact opens in the viewer.
3. **Artifact:** → "Make an HTML onboarding checklist" → generates sanitized HTML → renders in the viewer.
4. **Switch model:** sidebar → provider button → select "anthropic" → badge updates; next message uses the new backend.

## 4. Acceptance criteria

- [ ] Fresh clone → `docker compose up --build -d` → app at :8000 with sample data.
- [ ] Asking a question covered by a transcript returns an answer **with a citation**.
- [ ] Asking something not in the corpus returns an acknowledgement, not a fabricated answer.
- [ ] "Write a Ship 30 essay on …" returns a ~1,250-word, skimmable essay rendered as an artifact.
- [ ] "Make an HTML …" returns a rendered artifact with **no** `<script>` executing.
- [ ] Switching provider in the UI changes the badge and the next answer's backend.
- [ ] Stopping Ollama produces a graceful error/fallback, not a crash.
- [ ] `pytest -q` passes.

## 5. Implementation plan (what was built, in order)

1. Typed config + async DB models/schemas (contracts first).
2. Provider-agnostic LLM layer (Ollama/Anthropic/OpenAI) + factory/fallback.
3. RAG pipeline: chunker → embedder (with lexical fallback) → retriever → ingestion.
4. Agent loop + tools + Ship 30 / artifact skills + sanitization.
5. FastAPI routers (sessions, chat, config, ingest, artifacts) + logging/middleware.
6. Frontend SPA (chat, sessions, provider switcher, artifact viewer).
7. Docker Compose + `.env.example`.
8. Tests (unit + integration) and documentation.
