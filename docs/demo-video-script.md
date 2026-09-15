# 🎬 Demo Video Script — The Lenny Growth Assistant

**Length:** ~2:45–3:00 · **Camera:** on · **Model shown:** `ollama / qwen2.5:7b`  
*Record → upload to YouTube (unlisted is fine) → paste the link in the Google Form.*

> **Recording strategy:** Pre-load the first two answers before you hit record so you
> can show them instantly. For the remaining prompts (refusal, essay, HTML artifact),
> record yourself typing the question, then **fast-forward the wait in editing** and
> cut to the finished answer. This keeps the video tight and under 3 minutes.

---

## ⏱️ Timing Cheat Sheet

| Section | Time | Duration | Strategy |
|:--|:--:|:--:|:--|
| Hook | 0:00–0:20 | 20s | Face camera |
| Grounded chat (pre-loaded) | 0:20–1:00 | 40s | Show pre-loaded answers + scroll through citations |
| Honest refusal | 1:00–1:15 | 15s | Type → ⏩ fast-forward → show refusal |
| Ship 30 + artifacts | 1:15–1:50 | 35s | Type → ⏩ fast-forward → show essay + HTML artifact |
| Local Ollama | 1:50–2:30 | 40s | Terminal + badge + provider toggle |
| Trade-off + close | 2:30–3:00 | 30s | Face camera |

---

## 0:00–0:20 — Hook (the problem)

**[Face camera]**

> "Hi, I'm Ansuj. This is **The Lenny Growth Assistant**. Here's the problem: product and growth teams listen to Lenny's Podcast all the time, but that knowledge is trapped inside hour-long transcripts. You can't search it, you can't quote it, and you definitely can't reuse it. So I built a tool that turns those transcripts into a grounded, citable assistant — and it also *writes* for you."

---

## 0:20–1:00 — Grounded chat (pre-loaded answers)

**[Switch to the app — the chat already has 2 answers loaded]**

> "It's a full-stack app: FastAPI backend, React frontend, Postgres for storage, all running through Docker. Let me show you what the answers look like."

**[Scroll to the first answer: "What does Lenny say about finding product-market fit and positioning?"]**

> "I asked: *what does Lenny say about product-market fit and positioning?* — and notice the answer isn't just a summary, it's **grounded**. Every claim comes with a citation — the guest, the episode title, and the timestamp."

**[Click on / point at the citation chips in the drawer]**

> "So instead of trusting the AI, you can click straight through and verify it against the actual transcript. Here's Adam Grenier on growth channels, the PMF sample on the value hypothesis, and the positioning sample on category choice."

**[Scroll to the second answer: "How do I measure product-market fit?"]**

> "And it holds session context. I asked a follow-up — *how do I measure it?* — and it remembered what we were talking about and gave another grounded, cited answer."

---

## 1:00–1:15 — Honest refusal

**[Type: "What does Lenny say about quantum chromodynamics?"]**

> "Now, the part that matters most for trust — what happens when I ask something the transcripts *don't* cover?"

**[⏩ FAST-FORWARD in editing — cut to the finished answer]**

> "It **tells me it doesn't cover it** — it doesn't hallucinate an answer. That's the grounding guarantee."

---

## 1:15–1:50 — Ship 30 essay + artifacts

**[Type: "Write a Ship 30 for 30 essay on activation and retention"]**

> "The second requirement is reusable written content. I'll ask for a Ship 30 for 30 essay."

**[⏩ FAST-FORWARD in editing — cut to the artifact viewer open]**

> "A side-by-side **Artifact Viewer** opens with a roughly 1,250-word essay — hook, headings, bullets, bold takeaways — all grounded in the cited source material."

**[Type: "Make an HTML onboarding checklist for activation"]**

> "It also generates rendered artifacts."

**[⏩ FAST-FORWARD in editing — cut to the rendered HTML]**

> "Here's an HTML onboarding checklist rendered right inside the app. Everything is sanitized on the server and rendered in a sandboxed iframe, so even an HTML artifact can't run scripts."

---

## 1:50–2:30 — Local Ollama (the mandatory demo)

**[Open terminal, run `ollama list`]**

> "Now the part the assignment specifically requires: this is running **entirely locally**."

**[Point at `qwen2.5:7b` and `nomic-embed-text` in the output]**

> "Ollama is serving two models — `qwen2.5:7b` for chat, and `nomic-embed-text` for the retrieval embeddings."

**[Point at provider badge in the app header: `ollama · qwen2.5:7b`]**

> "You can see in the UI that the active provider is Ollama running qwen2.5 locally. No API keys, no cloud calls."

**[Open provider switcher, show options, switch back to Ollama]**

> "The config layer is swappable — I can flip to Anthropic or OpenAI from this dropdown without touching code — but for the demo I'll keep it on the local model."

---

## 2:30–2:50 — One technical trade-off

**[Face camera]**

> "One honest trade-off worth calling out: I'm storing embeddings as JSON in Postgres and computing similarity in Python, rather than using pgvector. For a demo corpus of a few hundred chunks, that's fast and keeps the Docker setup minimal. If this scaled to thousands of episodes, I'd swap in pgvector — it's a one-file change in the retriever, since the interface is already abstracted."

---

## 2:50–3:00 — Close

**[Face camera]**

> "That's The Lenny Growth Assistant. It's all in the repo — clone it, run `docker compose up`, and you can reproduce everything you just saw, fully local. Thanks for watching."

---

## ✅ Pre-Recording Setup

### Step 1 — Pre-load answers (do this BEFORE recording)
1. Open the app at `http://localhost:8000`
2. Click "New chat"
3. Ask: **"What does Lenny say about finding product-market fit and positioning?"**
4. Wait for the full answer (~120s)
5. Ask: **"How do I measure product-market fit?"**
6. Wait for the full answer (~120s)
7. Now you have a session with 2 grounded, cited answers ready to show

### Step 2 — Verify
- [ ] Both answers have citation chips visible
- [ ] Provider badge shows `ollama · qwen2.5:7b`
- [ ] Terminal open with `ollama list` ready to run

### Step 3 — Recording tools
- [ ] Screen recorder running (OBS / Loom / QuickTime)
- [ ] Camera on, audio checked
- [ ] **Record the full session** — you'll cut the wait times in editing

### Step 4 — Editing (post-recording)
For each ⏩ section:
- Keep the part where you type the question and start talking
- Cut out the 120s wait
- Resume at the finished answer
- A simple jump cut is fine — evaluators understand local model latency

## 🎯 The 5 Exact Prompts (Copy-Paste Ready)

```
What does Lenny say about finding product-market fit and positioning?
```
```
How do I measure product-market fit?
```
```
What does Lenny say about quantum chromodynamics?
```
```
Write a Ship 30 for 30 essay on activation and retention
```
```
Make an HTML onboarding checklist for activation
```
