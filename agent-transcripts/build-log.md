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
  `ChatPRD/lennys-podcast-transcripts` archive at runtime and ingests it
  (idempotent, raw files never committed). `ensure_corpus` runs on first boot,
  falling back to the bundled samples offline.
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

## Iteration 11 — Bug fixes & hardening from live QA

**What:** a real run surfaced four concrete defects plus an off-brand behavior:

1. **`datetime` SSE crash.** The streaming `done` event called
   `json.dumps(response.model_dump())`, but Pydantic v2's `model_dump()` returns
   `datetime` objects, so every streamed turn died with
   `Object of type datetime is not JSON serializable`.
   **Correction:** use `model_dump(mode="json")` (JSON-safe) in both SSE `done`
   emissions, plus a regression test that parses every `done` event as JSON.

2. **Chat area not scrollable.** The flex/grid containers lacked `min-height: 0`,
   so `.messages` grew past the viewport instead of scrolling (content clipped,
   only a horizontal code scrollbar visible).
   **Correction:** added `min-height: 0` to `.messages`, `.session-list`,
   `.artifact-body`, `.chat`, and `.artifact-panel`.

3. **No per-code-block copy button.** Only a hover “copy response” button existed.
   **Correction:** markdown code blocks are now wrapped in a ChatGPT-style header
   with a language label and a copy button (event-delegated, works for streaming
   responses and rendered artifacts).

4. **~5-minute first-response latency.** `resolve_provider()` ran a *full*
   completion as a healthcheck on every request — on a slow local model that's an
   entire extra generation per message. **Correction:** `OllamaProvider.healthcheck`
   now probes with `num_predict=1` (single token, milliseconds), the Anthropic/
   OpenAI providers use `max_tokens=1`, and `resolve_provider` caches probe results
   for 60s.

5. **Off-topic answers (e.g. “generate a tic tac toe game” → a tic-tac-toe
   implementation).** The system prompt now makes scope explicit (product/growth
   only, no code/games/general software), and a conservative deterministic scope
   guard short-circuits clearly off-topic requests *before* the model is invoked —
   returning a branded refusal instantly. Legitimate artifact requests (HTML
   checklist, landing page) are explicitly whitelisted from the guard.

**Result:** 40 tests pass, including the new scope-guard and JSON-serialization
regressions.

## Iteration 12 — React migration + final polish

**What:** a final review against the brief and a fresh-clone walkthrough surfaced a
stack/documentation mismatch and two real defects.

**Corrections:**
- **React + TypeScript + Vite frontend.** The earlier "vanilla JS, no build step"
  decision (Iterations 1 & 9) was reconsidered: the Artifact Viewer and token
  streaming are substantially cleaner with component state, and the Docker build
  compiles the SPA anyway — so there is no added evaluator friction. The frontend
  now lives in `frontend/` and is built to `backend/app/static/`. README,
  `architecture.md`, and `design.md` were updated to match (they previously still
  described a vanilla-JS SPA).
- **SSE event parsing bug.** The backend emits each stream event as JSON
  `{"type": "token|status|done|error", "data": …}` with no `event:` line, but the
  client keyed off the SSE `event:` field — so every event was silently dropped
  (no tokens, and `done` never fired, leaving the UI busy). Fixed the client to
  dispatch on the JSON `type` and read `data` (and `data.message`/`data.artifacts`
  for `done`).
- **Provider-toggle crash on 2nd switch.** `settings_store` wrote `app_settings`
  with `db.add`, so switching the provider a second time collided with the existing
  primary key and raised `IntegrityError`. Replaced with an idempotent upsert
  (`get` then update-or-insert) and added a regression test.
- **Docs/versioning alignment.** Bumped `main.py`/`pyproject.toml` to `0.2.0` to
  match the frontend; corrected "50 episodes on first boot" → "a starter set of 10
  (full pack via `POST /api/ingest/fetch`)"; removed stale "streaming deferred"
  and "typing indicator, not streaming" wording.

**Result:** 43 tests pass (3 new settings-store regressions).

## Verification

- `pytest -q` → **43 passed** (retrieval, speaker-turn chunking, security,
  ingestion, agent + skills + length enforcement, API validation + graceful LLM
  failure + streaming endpoint, agent-runtime selection, off-topic scope guard,
  SSE `done` JSON serialization, and settings-store upsert).
- Smoke test: server boots, `/health` and `/health/ready` return correct status,
  frontend + static assets serve, all 11 API routes registered in OpenAPI.

## Known, deliberate trade-offs

- **JSONB vs pgvector** — fine for demo-scale corpus; one-file swap to scale.
- **Two agent runtimes** (built-in loop + optional Claude Agent SDK) — a small amount
  of glue in exchange for satisfying both the "use the Claude Agent SDK" requirement
  and the "run keyless on Ollama" requirement.
- **Sample transcripts** — clearly-marked `[SAMPLE]` files so the demo runs offline;
  real Lenny transcripts must be ingested by the client (ingestion points at the
  public source).

## Iteration 11 — Corrected transcript data source and parser format

**What:** a review flagged that §3.3 of the assignment doc links the knowledge
base to [`ChatPRD/lennys-podcast-transcripts`](https://github.com/ChatPRD/lennys-podcast-transcripts),
but `fetch.py` was pulling from a *different* repo
(`LennysNewsletter/lennys-newsletterpodcastdata`) via an `index.json`. The correct
archive has no `index.json` and a different transcript format, so two coupled bugs
were introduced together:

1. **Wrong source** — `fetch.py` depended on `index.json` + a `podcasts/` filename
   convention that only exist in the wrong repo.
2. **Parser mismatch** — `chunker.py`'s `_TURN_LABEL_RE` only matched the
   `**Speaker** (HH:MM:SS):` bold-Markdown format. The ChatPRD archive uses
   `Speaker (HH:MM:SS):` for named turns and `(HH:MM:SS):` for timestamp-only
   continuations of the same speaker. The old regex matched *zero* turns on real
   transcripts, silently degrading to plain `chunk_text()` and dropping all
   speaker/timestamp citations.

**Corrections:**
- **Source** — rewrote `fetch.py` to enumerate `episodes/*/transcript.md` via the
  GitHub Git-Trees API and fetch each file from `raw.githubusercontent.com`.
  Removed the obsolete `include_newsletters` path and the `index.json` dependency.
  Metadata now comes from the archive's YAML frontmatter (`guest`, `title`,
  `publish_date`, `youtube_url`); `episode_id` is the guest slug.
- **Parser** — replaced `_TURN_LABEL_RE` with a line-anchored pattern that treats
  a timestamp-only line as a continuation of the current speaker. Whitespace is
  limited to `[ \t]` (never `\s`), so a label cannot span newlines and mis-attach
  the following text. A leading timestamp-only line before any named speaker is
  skipped rather than attributed to a fabricated speaker.
- **Tests** — updated speaker-turn tests to the real format and added regression
  cases for (a) timestamp-only continuation inheriting the speaker and (b) a
  leading timestamp-only line producing no turns.
- **Docs** — updated README, `docs/architecture.md`, and this log to point at the
  correct source and episode count (~300, not ~50).

**Failure / correction:** the first regex draft used `\s*` around the label and
matched across blank lines, causing a timestamp-only `(HH:MM:SS):` to swallow the
preceding paragraph. Tightened to `^[ \t]*` + `[ \t]+`/`[ \t]*` and anchored with
`re.MULTILINE`; the new regression tests pin this behavior.

## Iteration 12 — Full audit remediation (grounding, security, ops, migrations)

**What:** a complete code audit surfaced 15+ concrete issues across grounding,
security, LLM conversion, config, health, ops, and frontend. Fixes below.

**Corrections:**
- **Grounding signal** — `grounded` now means "this turn attached ≥1 source
  citation" (`bool(ctx.citations)`), not "the search tool was invoked". The
  built-in loop and the Claude SDK runtime now agree, and `generate_artifact`
  attaches citations for the passages it grounds on (previously only the essay
  skill did).
- **SSRF / KB poisoning** — `ingest_url` now validates http(s)+public-address
  only and re-validates every redirect hop, blocking loopback/private/link-local/
  metadata targets.
- **Provider switch** — `PUT /api/config` validates availability *before*
  persisting, so a failed switch no longer leaves the app on a broken provider.
- **Docker/Ollama** — the compose service now routes Ollama to the host via
  `host.docker.internal` (host-gateway) using a dedicated `OLLAMA_BASE_URL_DOCKER`
  var, instead of inheriting the host-`localhost` value from `.env` and pointing
  the container at itself.
- **Migrations** — added Alembic (async env, initial 0001 migration) wired into
  the Docker CMD; `AUTO_CREATE_TABLES=false` in the container, `create_all`
  retained for dev/tests.
- **Artifact safety** — the "open in new tab" path now re-sanitizes with DOMPurify
  and renders in a sandboxed iframe (`noopener`), closing the defense-in-depth gap.
- **Session ordering** — `_finalize_turn` now bumps `conversation.updated_at`.
- **Readiness** — `/health/ready` reports the *active* provider and returns 503
  when not ready.
- **Anthropic** — consecutive tool results are collapsed into a single user
  message (fixes multi-tool-turn 400s).
- **Retriever** — removed the "last resort returns an irrelevant chunk" branch;
  no-match now returns `[]` (honest "unsupported").
- **SSE client** — mid-stream transport failures no longer re-send the message
  (no duplicate turns); only the initial request falls back to non-streaming.
- **Errors/logging** — no internal exception text is leaked to clients; `LOG_LEVEL`
  is honored; `:focus-visible` + `prefers-reduced-motion` added.
- **Frontend tests** — added Vitest + jsdom with 6 tests (markdown XSS + SSE
  parsing) and a CI job.

**Failure / correction:** the first `_TURN_LABEL_RE`-style edit attempt hit a
whitespace mismatch (block indentation), which the atomic edit tool rejected; re-
applied with exact indentation. The Alembic migration was validated against
SQLite (`upgrade` + `downgrade base`) before committing.

**Result:** backend 48 passed; frontend 6 passed; `tsc` + `vite build` clean;
Alembic `upgrade head`/`downgrade base` verified on SQLite.

## Iteration 13 — Critical fix: demo corpus never seeded (empty knowledge base)

**What:** the user reported the assistant answering "I'm unable to find the
information you requested" for a basic prompt ("retention and activation").
Root cause was a path-resolution bug in `seed_samples`:

- `core/rag/ingest.py` lives at `backend/app/core/rag/ingest.py` (3 levels
  deep), but `seed_samples` used `parents[2]`, resolving to the non-existent
  `backend/app/data/transcripts`. It therefore always returned "Seed directory
  not found", so the bundled demo samples were **never** ingested.
- Combined with `ensure_corpus` only seeding samples when the network fetch
  produced *zero* sources, a fresh boot could end up with either an empty corpus
  (offline) or 10 alphabetically-random real episodes that don't cover the
  demo's suggested prompts (retention/activation/PMF/positioning).

**Corrections:**
- `seed_samples` now resolves `parents[3]` (the repo `backend/` directory).
- `ingest_directory` skips `README.md` (a data-directory note, not a transcript).
- `ensure_corpus` now **always seeds the bundled samples first** (they cover the
  four suggested prompts), then best-effort fetches real transcripts as
  enrichment — so the demo works offline and online.

**Failure / correction:** this was missed in the Iteration 12 audit because the
retrieval repro called `ingest_directory` directly with a correct path, masking
the broken `seed_samples` path. Added a regression test that calls
`seed_samples` itself and asserts 3 samples are seeded (README excluded).

**Result:** 49 tests pass; `seed_samples` seeds 3 sources/6 chunks; `ensure_corpus`
still seeds samples when the network fetch fails.

## Iteration 14 — Force grounding when a local model skips search

**What:** after the data-source + seed fixes, the demo still intermittently
returned "I'm unable to find the information you requested" — even though the
corpus had the answer. Root cause: a local Ollama model (llama3.1) sometimes
answers *without* invoking `search_transcripts` (especially on a cold start),
producing a vague or "can't find it" reply despite populated data.

**Corrections:**
- In the built-in agent loop, if the model returns a substantive answer with no
  tool calls and no citations this turn, the agent now runs `search_transcripts`
  itself and re-answers on the retrieved material (single bounded re-prompt).
  This guarantees every substantive answer is source-backed regardless of
  whether the model chose to search.
- Added a regression test: a model that answers "unable to find" without
  searching is still grounded (citations attached, grounded answer returned).

**Result:** 50 tests pass.

## Iteration 15 — Guarantee grounded answers regardless of model quality

**What:** after force-grounding (Iteration 14), a local model could still return
generic, uncited advice — e.g. "How do I know I've found product-market fit?" →
"customer validation, revenue growth, market size…" — even though the corpus
contains the right transcript. Root cause: weak local models (a) ignore JSON
retrieved payloads and (b) sometimes ignore the retrieved passages entirely and
synthesize generic advice.

**Corrections:**
- `agent.py` — grounding guarantee:
  1. Deterministically retrieves for any substantive question the model answered
     without searching.
  2. Re-answers on **readable, numbered passages** (not the JSON the tool returns).
  3. If the answer still does not cite a source (`[n]` marker or episode title),
     substitutes a **deterministic verbatim, source-tagged answer** built directly
     from the retrieved chunks.
  Also buffers the first-pass answer text so the un-grounded draft is never
  streamed to the client before it is replaced.
- `retriever.py` — fixed two latent issues: a `self._tokenize` typo in the BM25
  fallback (would `AttributeError` whenever the lexical path ran), and the
  embedding path now (a) only runs when real embeddings are available at query
  time (avoids mixing nomic vectors with lexical-hash fallback vectors) and
  (b) falls through to BM25 instead of returning empty on zero/negative cosine.
- `embedder.py` — added `real_embeddings_available()` so retrieval can detect
  the lexical-fallback (different vector space) case.
- Added regression test: a model that answers generically is replaced with the
  source-tagged answer.

**Result:** 51 tests pass.

## Iteration 16 — Close grounding gap when the search tool call fails

**What:** a fresh screenshot showed the assistant answering "It seems like the
search_transcripts function requires a specific format for the query parameter…
signs of PMF include growth, engagement, revenue…" — generic and uncited. Root
cause: llama3.1 called `search_transcripts` with a malformed `query` (nested
object / empty), the tool threw, and the model gave up and answered generically.
The prior grounding logic keyed off `"search_transcripts" in trace`, so a *failed*
search (invoked but zero citations) skipped deterministic retrieval AND the
fallback, letting the generic answer through.

**Corrections:**
- `agent.py` — deterministic retrieval now triggers on `not ctx.citations` (the
  turn has no retrieved citations) rather than "the tool wasn't invoked", so a
  failed search is still grounded.
- `tools.py` — `search_transcripts` now coerces `query` to a plain string (unwraps
  nested `{query}/{question}/{text}` objects) and `top_k` to an int, returning a
  graceful message instead of crashing on malformed tool-call arguments.
- Added regression test: a model that calls search with a malformed query and then
  answers generically still gets a source-tagged grounded answer.

**Result:** 52 tests pass.

## Iteration 17 — Stop the fallback from replacing good qwen answers

**What:** after switching to qwen2.5, a PMF + positioning question returned the
verbatim fallback ("Here's what Lenny's Podcast says…") instead of the model's
synthesis, and two of the three quoted chunks were off-topic. Root cause: the
grounding check only recognized `[n]` markers and the full title string, so a
legitimate citation by guest name / short title was treated as un-grounded and
the good answer was replaced.

**Corrections:**
- `agent.py` — `_mentions_source` now also accepts the title's topic portion
  ("X | Guest") and the guest/speaker name (excluding the host "Lenny", which
  appears in the question itself); the verbatim fallback now quotes the top-2
  chunks instead of 3 (drops trailing intro boilerplate).
- `retriever.py` — `RetrievedChunk.speaker` falls back to the source's guest name
  when a chunk has no per-turn speaker (plain-prose transcripts).
- Added regression test: a speaker-cited answer is kept, not replaced.

**Result:** 53 tests pass.

## Iteration 18 — Halve latency: retrieve-first, single-generation answers

**What:** with qwen2.5 the answers were finally grounded and cited, but the first
token arrived after ~120s. Root cause: the agent made two LLM generations per
question (model search → answer, or answer → deterministic re-answer), each ~60s
on CPU.

**Corrections:**
- `agent.py` — retrieve-first: for substantive questions the agent now retrieves
  the top passages *before* the model generates, injects them into the prompt
  (with an instruction not to re-search), and streams the single answer live. The
  reactive re-answer pass was removed. This drops a plain question to one
  generation (~60s) and makes grounding independent of tool-calling.
- `context.py` — `add_citation` dedupes by (source_id, chunk_index) so
  retrieve-first + a model-initiated search don't duplicate sources in the UI.
- Added regression tests: a plain question uses a single LLM call; a
  speaker-cited answer is not replaced by the fallback.

**Result:** 54 tests pass.

## Iteration 19 — Final polish: PMF disambiguation + default to qwen2.5:7b

**What:** final submission polish.

**Corrections:**
- `agent.py` — added an AMBIGUITY note so the model doesn't relabel an
  unrelated "PMF" (e.g. Adam Fishman's "People, Mission, Financials"
  job-evaluation framework) as product-market fit.
- Defaulted the local chat model to `qwen2.5:7b` (stronger tool-calling at a
  similar size to llama3.1) across `config.py`, `.env.example`, `run.sh`,
  README, architecture/demo/manual docs, and the provider modal; rebuilt the
  frontend static bundle to match.

**Result:** 54 tests pass; frontend builds clean.

## Iteration 20 — Compound-query retrieval (fix "PMF and positioning")

**What:** "What does Lenny say about product-market fit and positioning?" returned
solid PMF content but dropped the positioning half (surfaced Adriel Frederick's
algorithms chunk instead). Root cause: the query was embedded as a single blended
vector, which over-weighted the longer clause ("product-market fit") and let it
crowd out "positioning".

**Corrections:**
- `retriever.py` — `retrieve` now splits compound queries on "and"/"or"/"vs"/
  "versus", retrieves each clause separately, then merges + de-duplicates by
  (source, chunk) and re-ranks by score, so both topics are represented.
- Added regression test: "product-market fit and positioning" surfaces chunks for
  both clauses.

**Result:** 55 tests pass.

## Iteration 21 — Seed samples even when real transcripts already exist

**What:** "product-market fit and positioning" kept returning off-topic real
episodes (Adriel Frederick's algorithms, Alex Hardiman's NYT intro) with no
positioning content. Root cause: `ensure_corpus` seeded the bundled samples
(which cover the four demo prompts, incl. positioning) **only when the corpus was
empty**. Once real transcripts had been fetched, the early-return skipped
samples entirely, so "positioning" had no matching material.

**Corrections:**
- `fetch.py` — `ensure_corpus` now seeds the samples **before** the emptiness
  check (idempotent), and only the network fetch is skipped when real transcripts
  already exist.
- Added regression test: samples are seeded alongside pre-existing real
  transcripts.

**Result:** 56 tests pass.
