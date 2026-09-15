import React, { useEffect } from "react";
import { X, Check, AlertCircle } from "lucide-react";
import { AppConfig } from "../../utils/types";

interface ModelProviderModalProps {
  isOpen: boolean;
  onClose: () => void;
  config: AppConfig | null;
  onSelectProvider: (providerName: string) => Promise<void>;
}

export const ModelProviderModal: React.FC<ModelProviderModalProps> = ({
  isOpen,
  onClose,
  config,
  onSelectProvider,
}) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !config) return null;

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="modal-header">
          <h3>Inference Architecture</h3>
          <button
            onClick={onClose}
            className="workbench-btn"
            type="button"
            aria-label="Close dialog"
          >
            <X size={14} />
          </button>
        </div>

        {/* Body */}
        <div className="modal-body">
          <p style={{ fontSize: 12.5, color: "var(--text-secondary)", marginBottom: 6 }}>
            Toggle between local zero-dependency Ollama execution and Cloud models. Active backend updates immediately without restarting.
          </p>

          {config.providers.map((p) => {
            const isActive = p.name === config.provider;

            return (
              <div
                key={p.name}
                className={`provider-card ${isActive ? "active" : ""}`}
                onClick={() => {
                  if (p.available && !isActive) {
                    onSelectProvider(p.name);
                  }
                }}
                style={{
                  cursor: p.available && !isActive ? "pointer" : "default",
                  opacity: p.available ? 1 : 0.65,
                }}
              >
                <div>
                  <div className="provider-name" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span>{p.name}</span>
                    {isActive && <Check size={14} color="var(--accent)" />}
                  </div>
                  <div className="provider-sub">
                    {p.model || (p.reason ? p.reason : "No model configured")}
                  </div>
                </div>

                <div className={`provider-badge ${p.available ? "available" : "unavailable"}`}>
                  {p.available ? "Available" : "Unavailable"}
                </div>
              </div>
            );
          })}

          <div style={{ marginTop: 12, padding: "10px 12px", background: "var(--bg-app)", borderRadius: "var(--radius-sm)", display: "flex", gap: 8, alignItems: "flex-start", fontSize: 11.5, color: "var(--text-muted)" }}>
            <AlertCircle size={14} style={{ flexShrink: 0, marginTop: 1, color: "var(--accent)" }} />
            <span>
              Mandatory demo evaluation runs on local <strong>Ollama (qwen2.5:7b)</strong> keyless. Cloud providers require keys in your <code>.env</code>.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
