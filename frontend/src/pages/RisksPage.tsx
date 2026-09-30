import React, { useEffect, useState } from "react";
import { api } from "../api/client";
import { RiskReport } from "../types";

interface RisksProps {
  projectId: number;
}

export const RisksPage: React.FC<RisksProps> = ({ projectId }) => {
  const [report, setReport] = useState<RiskReport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      const data = await api.getRisks(projectId);
      setReport(data);
      setLoading(false);
    }
    load();
  }, [projectId]);

  if (loading || !report) {
    return <div className="card">Loading risk indicators...</div>;
  }

  return (
    <div>
      <div style={{ marginBottom: "20px" }}>
        <h2 style={{ fontSize: "1.4rem", fontWeight: 700 }}>Technical Risk Analysis</h2>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.88rem" }}>
          Deterministic, measurable risk indicators backed strictly by repository facts. No arbitrary AI scores.
        </p>
      </div>

      <div className="metrics-grid">
        <div className="metric-card">
          <span className="metric-title">Total Findings</span>
          <span className="metric-value">{report.total_findings}</span>
        </div>
        <div className="metric-card">
          <span className="metric-title" style={{ color: "var(--accent-rose)" }}>High Severity</span>
          <span className="metric-value" style={{ color: "var(--accent-rose)" }}>{report.high_count}</span>
        </div>
        <div className="metric-card">
          <span className="metric-title" style={{ color: "var(--accent-amber)" }}>Medium Severity</span>
          <span className="metric-value" style={{ color: "var(--accent-amber)" }}>{report.medium_count}</span>
        </div>
        <div className="metric-card">
          <span className="metric-title" style={{ color: "var(--accent-blue-light)" }}>Low / Info</span>
          <span className="metric-value" style={{ color: "var(--accent-blue-light)" }}>{report.low_count}</span>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
        {report.findings.map((finding, idx) => (
          <div
            key={idx}
            className="card"
            style={{
              borderLeft: `4px solid ${
                finding.severity === "HIGH"
                  ? "var(--accent-rose)"
                  : finding.severity === "MEDIUM"
                  ? "var(--accent-amber)"
                  : "var(--accent-blue)"
              }`,
            }}
          >
            <div className="card-title">
              <span>
                <strong style={{ fontSize: "1.05rem" }}>{finding.finding_type}</strong>: {finding.subject}
              </span>
              <span
                className={`badge ${
                  finding.severity === "HIGH"
                    ? "badge-high"
                    : finding.severity === "MEDIUM"
                    ? "badge-medium"
                    : "badge-low"
                }`}
              >
                {finding.severity}
              </span>
            </div>

            <p style={{ color: "var(--text-primary)", fontSize: "0.95rem", lineHeight: 1.5, marginBottom: "12px" }}>
              {finding.summary}
            </p>

            {/* Metrics */}
            {Object.keys(finding.metrics || {}).length > 0 && (
              <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", marginBottom: "12px", background: "rgba(0,0,0,0.2)", padding: "8px 12px", borderRadius: "var(--radius-sm)" }}>
                {Object.entries(finding.metrics).map(([k, v]) => (
                  <div key={k} style={{ fontSize: "0.8rem" }}>
                    <span style={{ color: "var(--text-muted)", textTransform: "capitalize" }}>{k.replace(/_/g, " ")}: </span>
                    <strong className="mono" style={{ color: "var(--accent-cyan)" }}>{String(v)}</strong>
                  </div>
                ))}
              </div>
            )}

            {/* Evidence */}
            {finding.evidence && finding.evidence.length > 0 && (
              <div>
                <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontWeight: 600 }}>Measurable Evidence:</span>
                <ul className="evidence-list">
                  {finding.evidence.map((ev, i) => (
                    <li key={i} className="evidence-item">
                      • {ev}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
