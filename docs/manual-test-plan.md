# Manual Test Plan — The Lenny Growth Assistant

Automated tests cover API, retrieval, ingestion, security, and agent routing
(`pytest -q`). This script covers the **UI** end-to-end.

**Preconditions:** stack running (`docker compose up --build -d`), Ollama up with
`llama3.1` + `nomic-embed-text` pulled, sample data seeded (automatic on first start).

| # | Action | Expected result | Pass? |
|---|---|---|---|
| 1 | Open http://localhost:8000 | App loads; sidebar shows "Lenny Growth / Assistant", "New chat", and 4 suggested prompts; provider badge shows `ollama · llama3.1`. | ☐ |
| 2 | Click "New chat" | Empty state appears; no artifacts panel. | ☐ |
| 3 | Click a suggested prompt (e.g. "product-market fit") | User bubble appears, a status indicator + streaming answer shows, then a grounded answer with **citation chips** (episode title + excerpt). | ☐ |
| 4 | Ask: "What does Lenny say about activation?" | Answer cites the retention/activation transcript; header title becomes the question. | ☐ |
| 5 | Ask a follow-up: "And how do I measure it?" | Answer uses conversation context (no re-explaining everything). | ☐ |
| 6 | Ask something unsupported: "What is quantum chromodynamics?" | Assistant says the KB doesn't cover it — **no fabricated answer, no fake citation**. | ☐ |
| 7 | Type "Write a Ship 30 for 30 essay on activation and retention" | Artifact panel opens beside chat with a ~1,250-word essay: hook, headings, bullets, bold, numbered points, takeaway. | ☐ |
| 8 | Type "Make an HTML checklist for onboarding activation" | Artifact panel shows a rendered HTML checklist (styled). Open dev tools: confirm **no `<script>` executes** (iframe is sandboxed). | ☐ |
| 9 | With multiple artifacts, click the tabs | Viewer switches between artifacts. | ☐ |
| 10 | Sidebar → provider button → select a provider | Dialog lists providers with available/unavailable state; active one highlighted; badge updates. | ☐ |
| 11 | Click "New chat" then an old session in the sidebar | Each session shows **only its own** messages + artifacts (independent context). | ☐ |
| 12 | Resize window below 900px | Layout remains usable and scrollable; the artifact panel closes via ✕. (A dedicated mobile drawer is a future enhancement.) | ☐ |
| 13 | Keyboard: Tab through the UI; Enter sends; Shift+Enter newline | All controls reachable and focus-visible; send works as expected. | ☐ |
| 13b | Sidebar → theme toggle | UI switches between light and dark; choice persists across reload. | ☐ |
| 13c | Click a citation card (after a grounded answer) | The source excerpt expands/collapses. | ☐ |
| 13d | Hover an assistant bubble → copy button; hover a session → delete | Copy puts the raw text on the clipboard; delete removes the session. | ☐ |
| 14 | Stop Ollama (`systemctl stop ollama` or quit the app), then send a message | Graceful error or fallback (if cloud keys set) — **no crash**; readiness endpoint shows degraded LLM. | ☐ |
| 15 | `docker compose down` then `up` | Sessions, messages, and artifacts persist (PostgreSQL volume). | ☐ |

**Negative-path extras:**
- `POST /api/sessions/{id}/messages` with `{"content": ""}` → `422`.
- `GET /api/sessions/nonexistent` → `404`.
- `GET /api/artifacts/nonexistent` → `404`.
