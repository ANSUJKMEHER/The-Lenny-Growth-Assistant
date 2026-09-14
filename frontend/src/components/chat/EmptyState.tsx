import React from "react";
import { ArrowUpRight } from "lucide-react";

interface EmptyStateProps {
  onSelectPrompt: (prompt: string) => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({ onSelectPrompt }) => {
  const briefs = [
    {
      title: "Activation & Retention Frameworks",
      desc: "Retrieve metrics, benchmarks, and retention curves discussed across Lenny's interviews.",
      prompt: "What does Lenny say about measuring product activation and retention?",
    },
    {
      title: "Product-Market Fit & Positioning",
      desc: "How Lenny and his guests define PMF, when to validate it, and how to position a product.",
      prompt: "What does Lenny say about finding product-market fit and positioning?",
    },
    {
      title: "Ship 30 for 30 Essay: Retention",
      desc: "Generate a ~1,250-word atomic essay formatted with hooks, bullet points, and core takeaways.",
      prompt: "Write a Ship 30 for 30 essay on activation and retention",
    },
    {
      title: "Interactive HTML Onboarding Checklist",
      desc: "Generate a standalone styled HTML checklist rendered inside the isolated artifact sandbox.",
      prompt: "Make an HTML checklist for improving onboarding activation",
    },
  ];

  return (
    <div className="empty-brief-container">
      <div className="brief-hero-header">
        <h2>Lenny Knowledge Retrieval &amp; Synthesis</h2>
        <p>Grounding across Lenny's Podcast transcripts with verifiable timestamps and artifact rendering.</p>
      </div>

      <div className="brief-prompts-grid">
        {briefs.map((b, i) => (
          <div
            key={i}
            className="brief-card"
            onClick={() => onSelectPrompt(b.prompt)}
            role="button"
            tabIndex={0}
          >
            <div className="brief-card-title">
              <span>{b.title}</span>
              <ArrowUpRight size={14} color="var(--accent)" />
            </div>
            <div className="brief-card-desc">{b.desc}</div>
          </div>
        ))}
      </div>
    </div>
  );
};
