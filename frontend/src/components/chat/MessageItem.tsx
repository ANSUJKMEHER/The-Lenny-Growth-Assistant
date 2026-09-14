import React, { useState } from "react";
import { Copy, Check } from "lucide-react";
import { Message } from "../../utils/types";
import { renderMarkdownToSafeHtml } from "../../utils/markdown";
import { CitationDrawer } from "./CitationDrawer";

interface MessageItemProps {
  message: Message;
}

export const MessageItem: React.FC<MessageItemProps> = ({ message }) => {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (isUser) {
    return (
      <div className="msg-row user">
        <div className="msg-bubble">{message.content}</div>
      </div>
    );
  }

  const html = renderMarkdownToSafeHtml(message.content);

  return (
    <div className="msg-row assistant">
      <div className="msg-bubble">
        <div
          className="prose"
          dangerouslySetInnerHTML={{ __html: html }}
        />

        {/* Citations section if present */}
        {message.citations && message.citations.length > 0 && (
          <CitationDrawer citations={message.citations} />
        )}

        {/* Action bar (Copy entire message) */}
        <div style={{ marginTop: 10, display: "flex", justifyContent: "flex-end" }}>
          <button
            onClick={handleCopy}
            type="button"
            className="code-copy-btn"
            title="Copy response text"
          >
            {copied ? <Check size={12} color="var(--ok)" /> : <Copy size={12} />}
            <span>{copied ? "Copied" : "Copy"}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
