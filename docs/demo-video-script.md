# 🎬 Demo Video Script — The Lenny Growth Assistant

**Length:** ~2:45–3:00 · **Camera:** on · **Model shown:** `ollama / qwen2.5:7b`  
*Record → upload to YouTube (unlisted is fine) → paste the link in the Google Form.*

---

## ⏱️ Timing Cheat Sheet

| Section | Time | Duration | What to show |
|:--|:--:|:--:|:--|
| Hook | 0:00–0:20 | 20s | Face camera — state the problem |
| Grounded chat | 0:20–1:10 | 50s | Ask → stream → citations → follow-up → honest refusal |
| Ship 30 + artifacts | 1:10–1:50 | 40s | Essay generation → artifact viewer → HTML artifact |
| Local Ollama | 1:50–2:30 | 40s | `ollama list` → badge → provider toggle |
| Trade-off | 2:30–2:50 | 20s | Face camera — explain pgvector decision |
| Close | 2:50–3:00 | 10s | Face camera — wrap up |

---

## 0:00–0:20 — Hook (the problem)

**[Screen: you, face camera]**

> "Hi, I'm Ansuj. This is **The Lenny Growth Assistant**. Here's the problem: product and growth teams listen to Lenny's Podcast all the time, but that knowledge is trapped inside hour-long transcripts. You can't search it, you can't quote it, and you definitely can't reuse it. So I built a tool that turns those transcripts into a grounded, citable assistant — and it also *writes* for you."

---

## 0:20–1:10 — Grounded chat (the core requirement)

**[Screen: switch to the running app at localhost:8000]**

> "It's a full-stack app: FastAPI on the backend, React on the frontend, Postgres for storage, all running through Docker."

**[Click "New chat", point at the 4 suggested prompts]**

> "You'll notice four suggested prompts — these map directly to what the assignment asked for."

**[Click the prompt: "What does Lenny say about finding product-market fit and positioning?"]**

> "I'll ask: *what does Lenny say about product-market fit and positioning?* Watch the answer stream in — and notice it's not just a summary, it's **grounded**."

**[Point at the citation chips / citation drawer as they appear]**

> "Every claim comes with a citation: the guest, the episode title, and the timestamp. So instead of trusting the AI, you can click straight through and verify it against the actual transcript."

**[Ask the follow-up: "How do I measure product-market fit?"]**

> "It also holds context. I can ask a follow-up like *how do I measure it?* — and it remembers what we were just talking about."

**[Ask an unsupported question: "What does Lenny say about quantum chromodynamics?"]**

> "And here's the part that matters most for trust: when I ask something the transcripts don't cover, it **tells me it doesn't cover it** — it doesn't hallucinate an answer."

---

## 1:10–1:50 — Ship 30 essay + artifact viewer

**[Type: "Write a Ship 30 for 30 essay on activation and retention"]**

> "The second requirement is reusable written content. So I'll ask it to write a Ship 30 for 30 essay on activation and retention."

**[Point at the Artifact Viewer opening beside the chat]**

> "A side-by-side **Artifact Viewer** opens, and it produces a roughly 1,250-word essay — hook, headings, bullets, bold takeaways — all grounded in the same cited source material, not generic marketing fluff."

**[Type: "Make an HTML onboarding checklist for activation"]**

> "It also generates rendered artifacts. Here I'll ask for an HTML onboarding checklist — and it renders as a styled document right inside the app."

**[Note the sandbox]**

> "Quick security note: everything is sanitized on the server with nh3 and rendered in a sandboxed iframe, so even an HTML artifact can't run scripts."

---

## 1:50–2:30 — Local Ollama (the mandatory demo)

**[Open a terminal, run `ollama list`]**

> "Now the part the assignment specifically requires: this is running **entirely locally**."

**[Point at terminal output showing `qwen2.5:7b` and `nomic-embed-text`]**

> "Ollama is serving two models — `qwen2.5:7b` for chat, and `nomic-embed-text` for the retrieval embeddings."

**[Point at the provider badge in the header: `ollama · qwen2.5:7b`]**

> "And you can see in the UI that the active provider is Ollama running qwen2.5 locally. No API keys, no cloud calls."

**[Open the provider switcher, show Anthropic/OpenAI options, then switch back to Ollama]**

> "The config layer is swappable — I can flip to Anthropic or OpenAI from this dropdown without touching code — but for the demo I'll keep it on the local model."

---

## 2:30–2:50 — One technical trade-off

**[Screen: you, face camera]**

> "One honest trade-off worth calling out: I'm storing embeddings as JSON in Postgres and computing similarity in Python, rather than using pgvector. For a demo corpus of a few hundred chunks, that's fast and keeps the Docker setup minimal — no native extensions to compile. If this scaled to thousands of episodes, I'd swap in pgvector — it's a one-file change in the retriever, since the interface is already abstracted."

---

## 2:50–3:00 — Close

**[Screen: you, face camera]**

> "That's The Lenny Growth Assistant. It's all in the repo — clone it, run `docker compose up`, and you can reproduce everything you just saw, fully local. Thanks for watching."

---

## ✅ Pre-Recording Checklist

- [ ] **Warm the model first** — ask one question before recording so the ~60s CPU latency doesn't eat your 3 minutes
- [ ] App running at `http://localhost:8000` with provider badge showing `ollama · qwen2.5:7b`
- [ ] Terminal open with `ollama list` ready to run
- [ ] Screen recording software running (OBS, Loom, or QuickTime)
- [ ] Camera on and positioned
- [ ] Audio check — speak clearly, moderate pace

## 🎯 Exact Prompts to Use (Pre-Verified)

Use these exact prompts — they're the ones you've already verified produce grounded, cited answers:

1. **"What does Lenny say about finding product-market fit and positioning?"** — compound query, shows both PMF + positioning citations
2. **"How do I measure product-market fit?"** — follow-up, shows session context
3. **"What does Lenny say about quantum chromodynamics?"** — honest refusal, shows trust
4. **"Write a Ship 30 for 30 essay on activation and retention"** — triggers the essay skill + artifact viewer
5. **"Make an HTML onboarding checklist for activation"** — triggers HTML artifact + shows sandbox security
