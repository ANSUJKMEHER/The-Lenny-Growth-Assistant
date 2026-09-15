# Demo Video Script (2–3 minutes, camera on)

*Record this, upload to YouTube, and add the link to the submission form.*

---

## 0:00–0:20 — The problem (hook)

> "Hi, I'm [name]. This is **The Lenny Growth Assistant**. The problem: product
> teams listen to Lenny's Podcast but can't *retrieve and reuse* what they heard —
> the knowledge is locked inside hour-long transcripts. I built a tool that turns
> those transcripts into a grounded, citable assistant that also *writes*."

## 0:20–1:10 — Show the product (grounded chat)

- Open the app, click a suggested prompt: *"What does Lenny say about product-market fit?"*
- Point out: status indicator + token streaming → a clear answer with **citation chips** showing the source episode.
- Ask a follow-up *"How do I measure it?"* → note it uses session context.
- Ask something unsupported → show it **says it doesn't cover it** instead of hallucinating.

## 1:10–1:45 — Ship 30 skill + artifact viewer

- Type *"Write a Ship 30 for 30 essay on activation"* → the **Artifact Viewer** opens
  beside the chat with a ~1,250-word skimmable essay (hook, headings, bullets, bold).
- Optionally: *"Make an HTML onboarding checklist"* → show the rendered HTML artifact.

## 1:45–2:30 — Local Ollama (the mandatory demo)

- Open a terminal: show `ollama list` (qwen2.5:7b + nomic-embed-text).
- In the app, show the **provider badge = `ollama / qwen2.5:7b`**.
- Switch to Anthropic in the UI (or note it's a toggle), then back to Ollama.
- Emphasize: **no API keys, fully local.**

## 2:30–3:00 — One technical trade-off

> "The one trade-off worth calling out: **embeddings are stored as JSON in Postgres
> and similarity is computed in Python, not pgvector.** For a demo corpus of a few
> hundred chunks that's fast and keeps Docker minimal. If this scaled to thousands
> of episodes, I'd swap to pgvector — it's a one-file change in the retriever."

**Close:** "Clone the repo, `docker compose up`, and you can run all of this locally.
Thanks for watching."
