import React, { useState } from "react";
import { api } from "../api/client";
import { AskResult } from "../types";

interface AskProps {
  projectId: number;
}

const SAMPLE_QUESTIONS = [
  "How does /api/payment reach the database?",
  "What does PaymentController depend on?",
  "Which components query the payments table?",
  "Does PaymentService have any circular dependencies?",
];

export const AskCodebasePage: React.FC<AskProps> = ({ projectId }) => {
  const [question, setQuestion] = useState("How does /api/payment reach the database?");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AskResult | null>(null);

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!question.trim()) return;

    setLoading(true);
    const data = await api.askQuestion(projectId, question.trim());
    setResult(data);
    setLoading(false);
  };

  return (
    <div>
      <div style={{ marginBottom: "20px" }}>
        <h2 style={{ fontSize: "1.4rem", fontWeight: 700 }}>Ask Codebase</h2>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.88rem" }}>
          Deterministic evidence-backed software intelligence Q&A. Operates without paid APIs or synthetic hallucination.
        </p>
      </div>

      <div className="card">
        <form onSubmit={handleSubmit} className="input-group">
          <input
            type="text"
            className="text-input"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask a question (e.g. How does /api/payment reach the database?)..."
          />
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? "Analyzing..." : "Ask"}
          </button>
        </form>

        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
          <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Suggested:</span>
          {SAMPLE_QUESTIONS.map((q, i) => (
            <button
              key={i}
              className="badge btn-secondary"
              style={{ cursor: "pointer" }}
              onClick={() => {
                setQuestion(q);
              }}
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      {result && (
        <div>
          {/* Answer Card */}
          <div className="card" style={{ borderLeft: "4px solid var(--accent-blue)" }}>
            <div className="card-title">
              <span>Answer</span>
              <span className="badge badge-verified">Evidence Grounded</span>
            </div>
            <p style={{ fontSize: "1.05rem", lineHeight: 1.6, color: "var(--text-primary)" }}>
              {result.answer}
            </p>
          </div>

          {/* Flow Trace if present */}
          {result.flow && result.flow.length > 0 && (
            <div className="card">
              <div className="card-title">Deterministic Request Flow Trace</div>
              <div className="flow-step-chain">
                {result.flow.map((step, idx) => (
                  <div key={idx} className="flow-step-box">
                    <span className="step-num">{step.step_number}</span>
                    <span className="badge badge-low">{step.node_kind}</span>
                    <strong style={{ fontSize: "0.95rem" }}>{step.node_name}</strong>
                    {step.relationship && (
                      <span className="mono" style={{ color: "var(--text-muted)", marginLeft: "auto" }}>
                        --[{step.relationship}]--&gt;
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Evidence */}
          {result.evidence && result.evidence.length > 0 && (
            <div className="card">
              <div className="card-title">Grounded Evidence Package</div>
              <ul className="evidence-list">
                {result.evidence.map((ev, i) => (
                  <li key={i} className="evidence-item">
                    {ev.symbol ? <strong>[{ev.symbol}] </strong> : null}
                    {ev.details || JSON.stringify(ev)}
                    {ev.file_path ? <span style={{ color: "var(--text-muted)" }}> ({ev.file_path})</span> : null}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Limitations */}
          {result.limitations && result.limitations.length > 0 && (
            <div className="card">
              <div className="card-title" style={{ color: "var(--accent-amber)" }}>
                Analysis Limitations
              </div>
              <ul style={{ paddingLeft: "20px", color: "var(--text-secondary)", fontSize: "0.85rem" }}>
                {result.limitations.map((lim, i) => (
                  <li key={i} style={{ marginBottom: "4px" }}>
                    {lim}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
