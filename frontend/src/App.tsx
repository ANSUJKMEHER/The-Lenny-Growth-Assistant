import React, { useState, useEffect, useRef } from "react";
import { Sidebar } from "./components/layout/Sidebar";
import { MessageItem } from "./components/chat/MessageItem";
import { EmptyState } from "./components/chat/EmptyState";
import { Composer } from "./components/chat/Composer";
import { ArtifactPanel } from "./components/artifacts/ArtifactPanel";
import { ModelProviderModal } from "./components/modal/ModelProviderModal";
import {
  fetchSessions,
  createSession,
  fetchSession,
  deleteSession,
  fetchConfig,
  updateConfig,
} from "./utils/api";
import { streamMessage } from "./utils/sse";
import { Session, Message, Artifact, AppConfig } from "./utils/types";
import { Loader2 } from "lucide-react";

export const App: React.FC = () => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [currentTitle, setCurrentTitle] = useState<string>("New conversation");
  const [messages, setMessages] = useState<Message[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [activeArtifactId, setActiveArtifactId] = useState<string | null>(null);
  const [isArtifactOpen, setIsArtifactOpen] = useState<boolean>(false);

  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [currentStepStatus, setCurrentStepStatus] = useState<string | null>(null);
  const [streamingContent, setStreamingContent] = useState<string>("");

  const [config, setConfig] = useState<AppConfig | null>(null);
  const [isModelModalOpen, setIsModelModalOpen] = useState(false);
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Initialize Theme
  useEffect(() => {
    const saved = localStorage.getItem("lenny-theme") as "dark" | "light" | null;
    const initialTheme = saved || "dark";
    setTheme(initialTheme);
    document.documentElement.setAttribute("data-theme", initialTheme);
  }, []);

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    localStorage.setItem("lenny-theme", next);
    document.documentElement.setAttribute("data-theme", next);
  };

  // Initial Load: Config & Sessions
  useEffect(() => {
    loadConfig();
    loadSessionsList();
  }, []);

  const loadConfig = async () => {
    try {
      const cfg = await fetchConfig();
      setConfig(cfg);
    } catch (e) {
      console.warn("Failed to load config:", e);
    }
  };

  const loadSessionsList = async () => {
    try {
      const list = await fetchSessions();
      setSessions(list);
      if (list.length > 0 && !currentSessionId) {
        handleSelectSession(list[0].id);
      }
    } catch (e) {
      console.warn("Failed to load sessions:", e);
    }
  };

  const handleSelectSession = async (id: string) => {
    try {
      setCurrentSessionId(id);
      const data = await fetchSession(id);
      setCurrentTitle(data.title || "Conversation");
      setMessages(data.messages || []);
      setArtifacts(data.artifacts || []);
      if (data.artifacts && data.artifacts.length > 0) {
        setActiveArtifactId(data.artifacts[data.artifacts.length - 1].id);
        setIsArtifactOpen(true);
      } else {
        setIsArtifactOpen(false);
      }
    } catch (e) {
      console.error("Failed to fetch session:", e);
    }
  };

  const handleNewChat = () => {
    setCurrentSessionId(null);
    setCurrentTitle("New conversation");
    setMessages([]);
    setArtifacts([]);
    setActiveArtifactId(null);
    setIsArtifactOpen(false);
    setStreamingContent("");
    setCurrentStepStatus(null);
  };

  const handleDeleteSession = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await deleteSession(id);
      const updated = sessions.filter((s) => s.id !== id);
      setSessions(updated);
      if (currentSessionId === id) {
        if (updated.length > 0) {
          handleSelectSession(updated[0].id);
        } else {
          handleNewChat();
        }
      }
    } catch (err) {
      console.error("Failed to delete session:", err);
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingContent, currentStepStatus]);

  const handleSendMessage = async (textToSend?: string) => {
    const prompt = (textToSend || input).trim();
    if (!prompt || busy) return;

    setInput("");
    setBusy(true);

    let activeId = currentSessionId;
    if (!activeId) {
      try {
        const created = await createSession(prompt.slice(0, 40));
        activeId = created.id;
        setCurrentSessionId(created.id);
        setCurrentTitle(created.title);
        setSessions((prev) => [created, ...prev]);
      } catch (err: any) {
        console.error("Session creation error:", err);
        setBusy(false);
        return;
      }
    }

    // Add user message to UI immediately
    const userMsg: Message = { role: "user", content: prompt };
    setMessages((prev) => [...prev, userMsg]);
    setStreamingContent("");
    setCurrentStepStatus("Analyzing request...");

    let accumulatedTokens = "";

    await streamMessage(activeId, prompt, {
      onStatus: (stepText) => {
        setCurrentStepStatus(stepText);
      },
      onToken: (token) => {
        accumulatedTokens += token;
        setStreamingContent((prev) => prev + token);
      },
      onDone: (doneMessage, newArtifacts) => {
        setCurrentStepStatus(null);
        setStreamingContent("");
        setMessages((prev) => [...prev, doneMessage]);

        if (newArtifacts && newArtifacts.length > 0) {
          setArtifacts((prev) => [...prev, ...newArtifacts]);
          setActiveArtifactId(newArtifacts[newArtifacts.length - 1].id);
          setIsArtifactOpen(true);
        }

        loadSessionsList();
        setBusy(false);
      },
      onError: (err) => {
        setCurrentStepStatus(null);
        setStreamingContent("");
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: `⚠️ **Error generating response:** ${err.message}`,
          },
        ]);
        setBusy(false);
      },
    });
  };

  const handleSelectProvider = async (providerName: string) => {
    try {
      const updated = await updateConfig(providerName);
      setConfig(updated);
      setIsModelModalOpen(false);
    } catch (e: any) {
      alert(`Could not switch provider: ${e.message}`);
    }
  };

  return (
    <div className="workstation">
      {/* Sidebar Rail */}
      <Sidebar
        sessions={sessions}
        currentSessionId={currentSessionId}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        onDeleteSession={handleDeleteSession}
        config={config}
        onOpenModelModal={() => setIsModelModalOpen(true)}
        theme={theme}
        onToggleTheme={toggleTheme}
      />

      {/* Center Chat Canvas */}
      <main className="main-canvas">
        <header className="canvas-header">
          <h1 className="canvas-title">{currentTitle}</h1>
          <div className="canvas-meta">
            {config && (
              <span className="canvas-badge">
                {config.provider} · {config.model || "standard"}
              </span>
            )}
          </div>
        </header>

        <div className="messages-viewport">
          {messages.length === 0 && !streamingContent && !busy ? (
            <EmptyState onSelectPrompt={(p) => handleSendMessage(p)} />
          ) : (
            <>
              {messages.map((m, idx) => (
                <MessageItem key={idx} message={m} />
              ))}

              {/* Streaming in progress */}
              {(currentStepStatus || streamingContent) && (
                <div className="msg-row assistant">
                  <div className="msg-bubble">
                    {currentStepStatus && (
                      <div className="step-indicator">
                        <Loader2 size={12} className="animate-spin" />
                        <span>{currentStepStatus}</span>
                      </div>
                    )}
                    {streamingContent && (
                      <MessageItem
                        message={{
                          role: "assistant",
                          content: streamingContent,
                        }}
                      />
                    )}
                  </div>
                </div>
              )}
            </>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Composer */}
        <Composer
          input={input}
          setInput={setInput}
          onSend={() => handleSendMessage()}
          busy={busy}
        />
      </main>

      {/* Right Artifact Workbench Panel */}
      {isArtifactOpen && artifacts.length > 0 && (
        <ArtifactPanel
          artifacts={artifacts}
          activeArtifactId={activeArtifactId}
          onSelectArtifact={(id) => setActiveArtifactId(id)}
          onClose={() => setIsArtifactOpen(false)}
        />
      )}

      {/* Model Switcher Modal */}
      <ModelProviderModal
        isOpen={isModelModalOpen}
        onClose={() => setIsModelModalOpen(false)}
        config={config}
        onSelectProvider={handleSelectProvider}
      />
    </div>
  );
};
