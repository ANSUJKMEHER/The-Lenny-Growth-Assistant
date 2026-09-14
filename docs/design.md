# Design — The Lenny Growth Assistant

UI/UX principles, information architecture, interaction states, responsive behavior,
accessibility, and the design decisions behind the frontend.

---

## 1. Principles

1. **Calm and focused.** One conversation, one artifact, muted neutrals. The
   interface should never compete with the answer. A single amber accent marks the
   interactive / "AI" affordances.
1. **Both light and dark.** A one-click theme toggle (persisted, defaults to dark) so
   the tool is comfortable in any environment.
2. **Trust is the product.** Every grounded answer shows its citations inline.
   The active model/provider is always visible (sidebar + header badge) so users
   know *what* they're talking to — a key requirement.
3. **Skimmable by default.** Answers render as clean Markdown: short paragraphs,
   headings, bullets, selective bold. Long prose walls are broken up.
4. **Zero-config for non-technical users.** Sample data is pre-seeded; the model
   toggle is a click, not a file edit; errors are written in plain language.
5. **Progressive disclosure.** The artifact viewer is hidden until there's an
   artifact; the provider dialog is hidden until asked; the empty state offers
   concrete suggested prompts.

## 2. Information architecture

```
Sidebar (280px)              Main chat                    Artifact panel (520px, optional)
├─ Brand                      ├─ Header: title + model     ├─ Header: "Artifact" + close
├─ "New chat"                 ├─ Message list              ├─ Tabs (one per artifact)
├─ Session list               ├─ Empty state + suggestions ├─ Body (markdown / iframe)
└─ Provider button            └─ Composer + hint
```

- **Left = context** (which chat, which model). **Center = conversation.**
  **Right = output** (the thing the user asked to *make*).
- Artifacts are shown **beside** the chat (not below, not in a new tab) per the
  "Artifact Viewer" requirement.

## 3. Key interaction states

| State | Treatment |
|---|---|
| Empty | Gradient hero mark + headline + 4 suggested prompt *cards* (icon + title + description; click → runs immediately). |
| Theme | Light/dark toggle in the sidebar footer; preference persisted, defaults to dark. |
| Sending | Composer disabled; live status ("Searching transcripts…") + token streaming in the assistant bubble. |
| Grounded answer | Assistant bubble + inline, **expandable** citation cards (source title + chevron → reveals the retrieved excerpt). |
| Ungrounded / refusal | Assistant clearly states the KB doesn't cover it (no fake citations). |
| Artifact ready | Panel slides in beside chat; latest artifact auto-selected; tabs for multiples. |
| Model switch | Dialog lists providers with live `available`/`unavailable` state; active one highlighted. |
| Error | Inline "something went wrong" message with the reason; a toast for transient UI errors. |
| Session hover | Each session row reveals a delete action; the active session is highlighted. |
| Loading sessions | Session list populates; latest session auto-opens. |

## 4. Responsive behavior

- **≥ 900px:** three-pane grid (sidebar · chat · artifact).
- **< 900px:** sidebar collapses into a drawer (☰ toggle); the artifact panel goes
  full-screen as an overlay with a close button. Chat remains the primary surface.
- The composer textarea auto-grows up to 200px; long messages scroll internally.

## 5. Accessibility

- Semantic landmarks (`aside`, `main`, `nav`, `header`), `<h1>`–`<h3>` hierarchy.
- All interactive elements are real `<button>`/`<textarea>` with `aria-label` where
  icon-only (send, close, sidebar toggle).
- Dialog uses `role="dialog"` + `aria-modal`; focusable via keyboard and dismissed with Esc.
- Visible `:focus-visible` outline; color contrast meets WCAG AA for text.
- `prefers-reduced-motion` disables animations.

## 6. Design decisions & rationale

- **React + TypeScript + Vite.** A single-page app built with Vite into static
  assets (served by FastAPI and baked into the Docker image). `marked` + `DOMPurify`
  are bundled at build time, so there is no CDN dependency at runtime and no
  framework lock-in for the evaluator.
- **Light + dark themes.** Dense text reads best on light surfaces; dark mode is
  offered for low-light environments. Both are driven by the same CSS variable
  system, so contrast stays consistent. Amber accent = clear brand signal.
- **Expandable citations.** The source title is always visible; the retrieved
  excerpt is revealed on click. This proves grounding on demand without cluttering
  the answer.
- **Inline actions.** Copy (responses + artifacts) and delete (sessions) are
  available where the user expects them — revealed on hover to keep the default
  view calm.
- **HTML artifacts in a sandboxed iframe, not `innerHTML`.** Guarantees isolation
  from the app origin regardless of sanitization; markdown artifacts (already
  sanitized) render as DOM for crisp typography.
- **Token streaming over SSE, with status updates.** The Ollama provider streams
  natively; other providers fall back to a single-shot chunk. Progress statuses
  ("Searching transcripts…", "Writing your essay…") keep the user informed during
  multi-tool turns.
- **Provider badge everywhere.** Surface "what model am I using" persistently, since
  the assignment makes it an explicit requirement and it builds user trust.
