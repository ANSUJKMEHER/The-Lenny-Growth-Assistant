import React from "react";
import { Plus, Trash2, Sun, Moon, Cpu } from "lucide-react";
import { Session, AppConfig } from "../../utils/types";

interface SidebarProps {
  sessions: Session[];
  currentSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  onDeleteSession: (id: string, e: React.MouseEvent) => void;
  config: AppConfig | null;
  onOpenModelModal: () => void;
  theme: "dark" | "light";
  onToggleTheme: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  sessions,
  currentSessionId,
  onSelectSession,
  onNewChat,
  onDeleteSession,
  config,
  onOpenModelModal,
  theme,
  onToggleTheme,
}) => {
  const activeProvider = config?.providers.find((p) => p.name === config.provider);
  const isAvailable = activeProvider?.available ?? false;

  return (
    <aside className="sidebar">
      {/* Brand Header */}
      <div className="sidebar-header">
        <div className="brand-badge">
          <div className="brand-icon">◆</div>
          <div>
            <div className="brand-title">Lenny Growth</div>
            <div className="brand-sub">Workbench v0.2</div>
          </div>
        </div>
      </div>

      {/* New Chat Button */}
      <button className="new-chat-btn" onClick={onNewChat} type="button">
        <Plus size={15} />
        <span>New conversation</span>
      </button>

      {/* Sessions Navigation */}
      <nav className="session-list" aria-label="Session history">
        {sessions.map((s) => (
          <div
            key={s.id}
            className={`session-item ${s.id === currentSessionId ? "active" : ""}`}
            onClick={() => onSelectSession(s.id)}
            role="button"
            tabIndex={0}
          >
            <span className="session-title">{s.title || "Untitled brief"}</span>
            <button
              className="session-delete-btn"
              onClick={(e) => onDeleteSession(s.id, e)}
              title="Delete session"
              type="button"
              aria-label="Delete session"
            >
              <Trash2 size={13} />
            </button>
          </div>
        ))}
      </nav>

      {/* Footer Controls */}
      <div className="sidebar-footer">
        <button
          className="model-trigger-btn"
          onClick={onOpenModelModal}
          type="button"
          title="Switch Model Provider"
        >
          <span className={`status-dot ${isAvailable ? "ok" : "warn"}`} />
          <Cpu size={13} style={{ marginRight: 2 }} />
          <span>{config ? `${config.provider} / ${config.model || "—"}` : "Connecting..."}</span>
        </button>

        <button
          className="theme-toggle-btn"
          onClick={onToggleTheme}
          type="button"
          title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          aria-label="Toggle theme"
        >
          {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
        </button>
      </div>
    </aside>
  );
};
