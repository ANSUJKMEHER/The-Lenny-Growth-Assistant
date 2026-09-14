import React, { useState } from "react";
import { ChevronDown, ChevronRight, ExternalLink, Bookmark } from "lucide-react";
import { Citation } from "../../utils/types";

interface CitationDrawerProps {
  citations: Citation[];
}

export const CitationDrawer: React.FC<CitationDrawerProps> = ({ citations }) => {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  if (!citations || citations.length === 0) return null;

  return (
    <div className="citations-wrapper">
      {citations.map((c, i) => {
        const isExpanded = expandedIndex === i;
        const guestText = c.guest ? `${c.guest} · ` : "";
        const timeText = c.timestamp ? `(${c.timestamp})` : "";

        return (
          <div key={i} className="citation-card">
            <div
              className="citation-bar"
              onClick={() => setExpandedIndex(isExpanded ? null : i)}
              role="button"
              tabIndex={0}
            >
              <div className="citation-headline">
                <Bookmark size={13} style={{ color: "var(--accent)", flexShrink: 0 }} />
                <span>
                  {c.title} {guestText && <span style={{ color: "var(--text-secondary)" }}>· {c.guest}</span>}
                </span>
                {timeText && <span className="citation-pill">{timeText}</span>}
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                {c.url && (
                  <a
                    href={c.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    style={{ color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 3, fontSize: 11 }}
                    title="Open original episode transcript"
                  >
                    <span>Source</span>
                    <ExternalLink size={11} />
                  </a>
                )}
                {isExpanded ? <ChevronDown size={14} color="var(--text-muted)" /> : <ChevronRight size={14} color="var(--text-muted)" />}
              </div>
            </div>

            {isExpanded && c.excerpt && (
              <div className="citation-excerpt">
                "{c.excerpt}"
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};
