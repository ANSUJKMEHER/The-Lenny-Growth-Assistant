/* The Lenny Growth Assistant — frontend.
 *
 * Vanilla JS (no build step) talking to the FastAPI backend. Handles sessions,
 * streaming-free chat, grounded citations (expandable), the provider switcher,
 * the side-by-side artifact viewer, light/dark theme, copy actions, and session
 * management.
 */
(() => {
  "use strict";

  // ------------------------------------------------------------------ //
  // State
  // ------------------------------------------------------------------ //
  const state = {
    sessions: [],
    currentSessionId: null,
    currentTitle: "New chat",
    config: null,
    artifacts: [], // artifacts in the current session
    activeArtifactId: null,
    busy: false,
  };

  // ------------------------------------------------------------------ //
  // DOM helpers
  // ------------------------------------------------------------------ //
  const $ = (sel) => document.querySelector(sel);
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };
  const icon = (id) => {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "i");
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", `#${id}`);
    svg.appendChild(use);
    return svg;
  };

  const messagesEl = $("#messages");
  const emptyStateEl = $("#emptyState");
  const sessionListEl = $("#sessionList");
  const inputEl = $("#input");
  const sendBtn = $("#sendBtn");
  const composer = $("#composer");
  const artifactPanel = $("#artifactPanel");
  const artifactTabs = $("#artifactTabs");
  const artifactBody = $("#artifactBody");
  const toastEl = $("#toast");

  // marked + DOMPurify are loaded as globals by the vendor <script> tags.
  marked.setOptions({ breaks: true, gfm: true });

  function showToast(text, ms = 3200) {
    toastEl.textContent = text;
    toastEl.hidden = false;
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => (toastEl.hidden = true), ms);
  }

  function sanitize(html) {
    return DOMPurify.sanitize(html, { USE_PROFILES: { html: true } });
  }

  function renderMarkdown(md) {
    return sanitize(marked.parse(md || ""));
  }

  async function copyText(text, label) {
    try {
      await navigator.clipboard.writeText(text);
      showToast(label || "Copied to clipboard");
      return true;
    } catch (err) {
      showToast("Could not copy — clipboard unavailable");
      return false;
    }
  }

  // ------------------------------------------------------------------ //
  // Theme
  // ------------------------------------------------------------------ //
  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("lenny-theme", theme);
    } catch (_) {
      /* ignore */
    }
  }

  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") || "light";
  }

  function initTheme() {
    let saved = null;
    try {
      saved = localStorage.getItem("lenny-theme");
    } catch (_) {
      /* ignore */
    }
    if (saved === "dark" || saved === "light") {
      applyTheme(saved);
    } else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
      applyTheme("dark");
    } else {
      applyTheme("light");
    }
  }

  // ------------------------------------------------------------------ //
  // API
  // ------------------------------------------------------------------ //
  async function api(path, options = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (res.status === 204) return null;
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = data.detail || data.error || `Request failed (${res.status})`;
      throw new Error(msg);
    }
    return data;
  }

  // ------------------------------------------------------------------ //
  // Rendering
  // ------------------------------------------------------------------ //
  function renderSessions() {
    sessionListEl.innerHTML = "";
    for (const s of state.sessions) {
      const btn = el("button", "session-item", s.title || "New chat");
      btn.type = "button";
      if (s.id === state.currentSessionId) btn.classList.add("active");
      btn.addEventListener("click", () => selectSession(s.id));

      const del = el("button", "session-delete");
      del.type = "button";
      del.setAttribute("aria-label", `Delete session ${s.title || "New chat"}`);
      del.title = "Delete session";
      del.appendChild(icon("icon-trash"));
      del.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteSession(s.id);
      });

      btn.appendChild(del);
      sessionListEl.appendChild(btn);
    }
  }

  function appendMessage(role, content, citations) {
    const wrap = el("div", `msg ${role}`);

    // Avatar
    const avatar = el("div", "msg-avatar");
    avatar.setAttribute("aria-hidden", "true");
    avatar.appendChild(icon(role === "user" ? "icon-user" : "icon-logo"));
    wrap.appendChild(avatar);

    const contentWrap = el("div", "msg-content");

    const body = el("div", "msg-body prose");
    body.innerHTML = renderMarkdown(content);
    contentWrap.appendChild(body);

    if (role === "assistant") {
      contentWrap.appendChild(buildActions(content));
    }

    if (citations && citations.length) {
      contentWrap.appendChild(buildCitations(citations));
    }

    wrap.appendChild(contentWrap);
    messagesEl.appendChild(wrap);
    scrollToBottom();
    return wrap;
  }

  function buildActions(content) {
    const actions = el("div", "msg-actions");
    const copy = el("button", "msg-action");
    copy.type = "button";
    copy.setAttribute("aria-label", "Copy response");
    copy.title = "Copy response";
    copy.appendChild(icon("icon-copy"));
    copy.addEventListener("click", async () => {
      const ok = await copyText(content, "Response copied");
      if (ok) {
        copy.classList.add("done");
        copy.replaceChildren(icon("icon-check"));
        setTimeout(() => {
          copy.classList.remove("done");
          copy.replaceChildren(icon("icon-copy"));
        }, 1600);
      }
    });
    actions.appendChild(copy);
    return actions;
  }

  function buildCitations(citations) {
    const box = el("div", "citations");
    box.appendChild(el("div", "citations-label", "Sources"));
    for (const c of citations) {
      const cite = el("div", "citation");
      const head = el("button", "citation-head");
      head.type = "button";
      head.setAttribute("aria-expanded", "false");
      head.appendChild(el("span", "citation-title", c.title));
      const chevron = el("span", "citation-chevron");
      chevron.appendChild(icon("icon-chevron"));
      head.appendChild(chevron);

      const excerpt = el("div", "citation-excerpt", c.excerpt || "");
      head.addEventListener("click", () => {
        const open = cite.classList.toggle("open");
        head.setAttribute("aria-expanded", String(open));
      });
      cite.appendChild(head);
      cite.appendChild(excerpt);
      box.appendChild(cite);
    }
    return box;
  }

  function appendTyping() {
    const wrap = el("div", "msg assistant");
    const avatar = el("div", "msg-avatar");
    avatar.setAttribute("aria-hidden", "true");
    avatar.appendChild(icon("icon-logo"));
    wrap.appendChild(avatar);

    const contentWrap = el("div", "msg-content");
    const body = el("div", "msg-body");
    const typing = el("span", "typing");
    typing.innerHTML = "<span></span><span></span><span></span>";
    body.appendChild(typing);
    contentWrap.appendChild(body);
    wrap.appendChild(contentWrap);

    messagesEl.appendChild(wrap);
    scrollToBottom();
    return wrap;
  }

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function updateHeader() {
    $("#chatTitle").textContent = state.currentTitle || "New chat";
  }

  function renderProviderBadge() {
    if (!state.config) return;
    const c = state.config;
    $("#providerLabel").textContent = `${c.provider} · ${c.model || "—"}`;
    $("#modelBadgeText").textContent = `${c.provider} / ${c.model || "—"}`;
    const active = c.providers.find((p) => p.name === c.provider);
    const available = active && active.available;
    const dot = $("#providerDot");
    dot.className = "status-dot " + (available ? "ok" : "warn");
    const badgeDot = $(".model-badge-dot");
    if (badgeDot) badgeDot.classList.toggle("warn", !available);
  }

  // ------------------------------------------------------------------ //
  // Artifacts
  // ------------------------------------------------------------------ //
  function setArtifacts(artifacts) {
    state.artifacts = artifacts || [];
    if (state.artifacts.length === 0) {
      artifactPanel.hidden = true;
      return;
    }
    artifactPanel.hidden = false;
    if (!state.activeArtifactId || !state.artifacts.some((a) => a.id === state.activeArtifactId)) {
      state.activeArtifactId = state.artifacts[state.artifacts.length - 1].id;
    }
    renderArtifactTabs();
    renderActiveArtifact();
  }

  function renderArtifactTabs() {
    artifactTabs.innerHTML = "";
    state.artifacts.forEach((a) => {
      const tab = el("button", "artifact-tab", a.title);
      tab.type = "button";
      tab.setAttribute("role", "tab");
      if (a.id === state.activeArtifactId) tab.classList.add("active");
      tab.addEventListener("click", () => {
        state.activeArtifactId = a.id;
        renderArtifactTabs();
        renderActiveArtifact();
      });
      artifactTabs.appendChild(tab);
    });
  }

  function renderActiveArtifact() {
    const a = state.artifacts.find((x) => x.id === state.activeArtifactId);
    if (!a) return;
    $("#artifactTitle").textContent = a.title;
    artifactBody.innerHTML = "";

    if (a.kind === "html") {
      // Untrusted HTML -> isolated, script-disabled, same-origin-less iframe.
      const frame = el("iframe", "artifact-frame");
      frame.setAttribute("sandbox", "");
      frame.setAttribute("referrerpolicy", "no-referrer");
      frame.setAttribute("title", a.title);
      frame.srcdoc = a.content;
      artifactBody.appendChild(frame);
    } else {
      const div = el("div", "prose");
      div.innerHTML = renderMarkdown(a.content);
      artifactBody.appendChild(div);
    }
  }

  // ------------------------------------------------------------------ //
  // Sessions
  // ------------------------------------------------------------------ //
  async function loadSessions() {
    const data = await api("/api/sessions");
    state.sessions = data.sessions || [];
    renderSessions();
  }

  async function selectSession(id) {
    const data = await api(`/api/sessions/${id}`);
    state.currentSessionId = id;
    state.currentTitle = data.title;
    updateHeader();
    renderSessions();
    renderConversation(data);
  }

  function renderConversation(data) {
    messagesEl.innerHTML = "";
    for (const m of data.messages || []) {
      appendMessage(m.role, m.content, m.citations);
    }
    emptyStateEl.style.display = "none";
    setArtifacts(data.artifacts);
    if (!(data.messages || []).length) {
      messagesEl.appendChild(emptyStateEl);
      emptyStateEl.style.display = "";
    }
  }

  async function newChat() {
    state.currentSessionId = null;
    state.currentTitle = "New chat";
    state.artifacts = [];
    state.activeArtifactId = null;
    artifactPanel.hidden = true;
    updateHeader();
    renderSessions();
    messagesEl.innerHTML = "";
    messagesEl.appendChild(emptyStateEl);
    emptyStateEl.style.display = "";
    inputEl.focus();
  }

  async function deleteSession(id) {
    try {
      await api(`/api/sessions/${id}`, { method: "DELETE" });
      showToast("Session deleted");
      if (state.currentSessionId === id) {
        state.currentSessionId = null;
        await newChat();
      }
      await loadSessions();
    } catch (err) {
      showToast(`Could not delete: ${err.message}`);
    }
  }

  // ------------------------------------------------------------------ //
  // Send message
  // ------------------------------------------------------------------ //
  async function sendMessage(text) {
    if (state.busy || !text.trim()) return;
    state.busy = true;
    sendBtn.disabled = true;
    emptyStateEl.style.display = "none";

    appendMessage("user", text);

    // Ensure a session exists.
    if (!state.currentSessionId) {
      const created = await api("/api/sessions", {
        method: "POST",
        body: JSON.stringify({ title: null }),
      });
      state.currentSessionId = created.id;
      state.currentTitle = created.title;
      updateHeader();
    }

    const typingEl = appendTyping();
    try {
      const res = await api(`/api/sessions/${state.currentSessionId}/messages`, {
        method: "POST",
        body: JSON.stringify({ content: text }),
      });
      typingEl.remove();
      appendMessage("assistant", res.message.content, res.message.citations);
      state.currentTitle = state.currentTitle === "New chat"
        ? (text.slice(0, 60) || "New chat")
        : state.currentTitle;
      updateHeader();
      if (res.artifacts && res.artifacts.length) {
        setArtifacts([...state.artifacts, ...res.artifacts]);
        state.activeArtifactId = res.artifacts[res.artifacts.length - 1].id;
        renderArtifactTabs();
        renderActiveArtifact();
      }
      await loadSessions();
    } catch (err) {
      typingEl.remove();
      appendMessage("assistant", `⚠️ **Something went wrong.**\n\n${err.message}`);
    } finally {
      state.busy = false;
      sendBtn.disabled = false;
      inputEl.focus();
    }
  }

  // ------------------------------------------------------------------ //
  // Provider switcher
  // ------------------------------------------------------------------ //
  async function loadConfig() {
    try {
      state.config = await api("/api/config");
      renderProviderBadge();
      renderProviderDialog();
    } catch (err) {
      $("#providerLabel").textContent = "unavailable";
    }
  }

  function renderProviderDialog() {
    const box = $("#providerOptions");
    box.innerHTML = "";
    const active = state.config ? state.config.provider : null;
    for (const p of state.config.providers) {
      const opt = el("div", "provider-option" + (p.name === active ? " active" : ""));
      const left = el("div");
      left.appendChild(el("div", "name", p.name));
      left.appendChild(el("div", "detail", p.model || "no model set"));
      const stateBadge = el(
        "span",
        "state " + (p.available ? "available" : "unavailable"),
        p.available ? "available" : "unavailable"
      );
      opt.appendChild(left);
      opt.appendChild(stateBadge);
      if (p.available && p.name !== active) {
        opt.classList.add("clickable");
        opt.addEventListener("click", () => switchProvider(p.name));
      }
      box.appendChild(opt);
    }
  }

  async function switchProvider(name) {
    try {
      await api("/api/config", {
        method: "PUT",
        body: JSON.stringify({ provider: name }),
      });
      await loadConfig();
      showToast(`Switched provider to ${name}.`);
    } catch (err) {
      showToast(`Could not switch: ${err.message}`);
    }
  }

  // ------------------------------------------------------------------ //
  // Events
  // ------------------------------------------------------------------ //
  composer.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = inputEl.value;
    inputEl.value = "";
    autoGrow();
    sendMessage(text);
  });

  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      composer.requestSubmit();
    }
  });

  function autoGrow() {
    inputEl.style.height = "auto";
    inputEl.style.height = Math.min(inputEl.scrollHeight, 200) + "px";
  }
  inputEl.addEventListener("input", autoGrow);

  $("#newChatBtn").addEventListener("click", newChat);
  $("#closeArtifact").addEventListener("click", () => (artifactPanel.hidden = true));
  $("#copyArtifact").addEventListener("click", () => {
    const a = state.artifacts.find((x) => x.id === state.activeArtifactId);
    if (a) copyText(a.content, "Artifact copied");
  });

  $("#themeToggle").addEventListener("click", () => {
    applyTheme(currentTheme() === "dark" ? "light" : "dark");
  });

  $("#providerBtn").addEventListener("click", () => {
    loadConfig();
    $("#providerDialog").hidden = false;
  });
  $("#closeProviderDialog").addEventListener("click", () => {
    $("#providerDialog").hidden = true;
  });
  $("#providerDialog").addEventListener("click", (e) => {
    if (e.target === $("#providerDialog")) $("#providerDialog").hidden = true;
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("#providerDialog").hidden) {
      $("#providerDialog").hidden = true;
    }
  });

  // Suggestion chips.
  document.querySelectorAll(".suggestion").forEach((btn) => {
    btn.addEventListener("click", () => {
      const prompt = btn.dataset.prompt;
      inputEl.value = prompt;
      autoGrow();
      sendMessage(prompt);
    });
  });

  // Sidebar toggle (mobile).
  $("#sidebarToggle").addEventListener("click", () => {
    $("#sidebar").classList.toggle("open");
  });

  // ------------------------------------------------------------------ //
  // Init
  // ------------------------------------------------------------------ //
  (async function init() {
    initTheme();
    await Promise.all([loadConfig(), loadSessions()]);
    if (state.sessions.length) {
      await selectSession(state.sessions[0].id);
    }
  })().catch((err) => {
    console.error("init failed", err);
    showToast("Failed to initialise: " + err.message);
  });
})();
