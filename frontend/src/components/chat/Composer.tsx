import React, { useRef, useEffect } from "react";
import { ArrowUp } from "lucide-react";

interface ComposerProps {
  input: string;
  setInput: (val: string) => void;
  onSend: () => void;
  busy: boolean;
}

export const Composer: React.FC<ComposerProps> = ({
  input,
  setInput,
  onSend,
  busy,
}) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  }, [input]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!busy && input.trim()) {
        onSend();
      }
    }
  };

  return (
    <div className="composer-container">
      <div className="composer-box">
        <textarea
          ref={textareaRef}
          className="composer-textarea"
          rows={1}
          placeholder="Ask a question about growth, retention, or request an artifact..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={busy}
          aria-label="Message input"
        />

        <div className="composer-actions">
          <div className="composer-hints">
            <span>↵ Send</span> · <span>⇧↵ New line</span>
          </div>

          <button
            className="send-btn"
            onClick={onSend}
            disabled={busy || !input.trim()}
            type="button"
            aria-label="Send message"
          >
            <span>Execute</span>
            <ArrowUp size={14} />
          </button>
        </div>
      </div>
    </div>
  );
};
