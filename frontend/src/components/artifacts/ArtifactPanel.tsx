import React, { useState } from "react";
import { X, Copy, Download, ExternalLink, Check, FileText, Code } from "lucide-react";
import { Artifact } from "../../utils/types";
import { renderMarkdownToSafeHtml } from "../../utils/markdown";

interface ArtifactPanelProps {
  artifacts: Artifact[];
  activeArtifactId: string | null;
  onSelectArtifact: (id: string) => void;
  onClose: () => void;
}

export const ArtifactPanel: React.FC<ArtifactPanelProps> = ({
  artifacts,
  activeArtifactId,
  onSelectArtifact,
  onClose,
}) => {
  const [copied, setCopied] = useState(false);
  const [viewSource, setViewSource] = useState(false);

  if (!artifacts || artifacts.length === 0) return null;

  const currentArtifact =
    artifacts.find((a) => a.id === activeArtifactId) || artifacts[artifacts.length - 1];

  const handleCopy = () => {
    navigator.clipboard.writeText(currentArtifact.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const ext = currentArtifact.kind === "html" ? "html" : "md";
    const filename = `${currentArtifact.title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.${ext}`;
    const blob = new Blob([currentArtifact.content], {
      type: currentArtifact.kind === "html" ? "text/html" : "text/markdown",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleOpenInNewTab = () => {
    if (currentArtifact.kind === "html") {
      const win = window.open("", "_blank");
      if (win) {
        win.document.write(currentArtifact.content);
        win.document.close();
      }
    } else {
      const blob = new Blob([currentArtifact.content], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank");
    }
  };

  return (
    <aside className="artifact-workbench" aria-label="Artifact Workbench">
      {/* Workbench Header */}
      <div className="workbench-header">
        <div className="workbench-tabs">
          {artifacts.map((a) => (
            <button
              key={a.id}
              className={`workbench-tab ${a.id === currentArtifact.id ? "active" : ""}`}
              onClick={() => onSelectArtifact(a.id)}
              type="button"
              title={a.title}
            >
              <FileText size={12} style={{ display: "inline", marginRight: 4 }} />
              {a.title}
            </button>
          ))}
        </div>

        {/* Action Controls */}
        <div className="workbench-controls">
          {currentArtifact.kind === "html" && (
            <button
              className="workbench-btn"
              onClick={() => setViewSource(!viewSource)}
              title={viewSource ? "View Rendered Preview" : "View HTML Source"}
              type="button"
            >
              <Code size={12} />
              <span>{viewSource ? "Preview" : "Source"}</span>
            </button>
          )}

          <button
            className="workbench-btn"
            onClick={handleCopy}
            title="Copy content"
            type="button"
          >
            {copied ? <Check size={12} color="var(--ok)" /> : <Copy size={12} />}
            <span>{copied ? "Copied" : "Copy"}</span>
          </button>

          <button
            className="workbench-btn"
            onClick={handleDownload}
            title="Download artifact"
            type="button"
          >
            <Download size={12} />
            <span>Save</span>
          </button>

          <button
            className="workbench-btn"
            onClick={handleOpenInNewTab}
            title="Open in new tab"
            type="button"
          >
            <ExternalLink size={12} />
          </button>

          <button
            className="workbench-btn"
            onClick={onClose}
            title="Close workbench"
            type="button"
            style={{ marginLeft: 4 }}
          >
            <X size={13} />
          </button>
        </div>
      </div>

      {/* Workbench Body */}
      <div className="workbench-body">
        {currentArtifact.kind === "html" && !viewSource ? (
          // Untrusted HTML strictly isolated via sandbox (no script execution permitted)
          <iframe
            className="sandboxed-frame"
            sandbox=""
            referrerPolicy="no-referrer"
            title={currentArtifact.title}
            srcDoc={currentArtifact.content}
          />
        ) : (
          <div
            className="prose"
            dangerouslySetInnerHTML={{
              __html: renderMarkdownToSafeHtml(
                currentArtifact.kind === "html"
                  ? `\`\`\`html\n${currentArtifact.content}\n\`\`\``
                  : currentArtifact.content
              ),
            }}
          />
        )}
      </div>
    </aside>
  );
};
