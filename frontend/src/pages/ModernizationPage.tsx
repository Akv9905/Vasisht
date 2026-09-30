import React, { useEffect, useState } from "react";
import { api } from "../api/client";
import { ModernizationReport } from "../types";

interface ModProps {
  projectId: number;
}

export const ModernizationPage: React.FC<ModProps> = ({ projectId }) => {
  const [report, setReport] = useState<ModernizationReport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      const data = await api.getModernization(projectId);
      setReport(data);
      setLoading(false);
    }
    load();
  }, [projectId]);

  if (loading || !report) {
    return <div className="card">Loading modernization opportunities...</div>;
  }

  return (
    <div>
      <div style={{ marginBottom: "20px" }}>
        <h2 style={{ fontSize: "1.4rem", fontWeight: 700 }}>Evidence-Backed Modernization</h2>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.88rem" }}>
          Targeted architectural modernization candidates derived from static coupling, cycles, and testing boundaries.
        </p>
      </div>

      <div className="metrics-grid">
        <div className="metric-card">
          <span className="metric-title">Candidates Identified</span>
          <span className="metric-value">{report.total_findings}</span>
          <span className="metric-desc">Ranked by investigation priority</span>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "18px" }}>
        {report.findings.map((item, idx) => (
          <div key={idx} className="card" style={{ borderLeft: "4px solid var(--accent-purple)" }}>
            <div className="card-title">
              <span>
                <span className="badge badge-verified" style={{ marginRight: 8 }}>
                  #{item.suggested_investigation_order}
                </span>
                <strong style={{ fontSize: "1.05rem" }}>{item.finding}</strong>
              </span>
              <span className="badge badge-low">{item.category}</span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", marginBottom: "14px" }}>
              <div style={{ background: "rgba(0,0,0,0.2)", padding: "12px", borderRadius: "var(--radius-sm)" }}>
                <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontWeight: 600, marginBottom: "4px" }}>
                  ARCHITECTURAL REASON
                </div>
                <p style={{ fontSize: "0.88rem", color: "var(--text-secondary)" }}>{item.reason}</p>
              </div>

              <div style={{ background: "rgba(16, 185, 129, 0.05)", border: "1px solid rgba(16, 185, 129, 0.2)", padding: "12px", borderRadius: "var(--radius-sm)" }}>
                <div style={{ fontSize: "0.8rem", color: "var(--accent-emerald)", fontWeight: 600, marginBottom: "4px" }}>
                  POSSIBLE MODERNIZATION DIRECTION
                </div>
                <p style={{ fontSize: "0.88rem", color: "var(--text-primary)" }}>{item.possible_direction}</p>
              </div>
            </div>

            {/* Evidence & Dependencies */}
            <div style={{ marginBottom: "12px" }}>
              <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontWeight: 600 }}>Supporting Evidence:</div>
              <ul className="evidence-list">
                {item.evidence.map((ev, i) => (
                  <li key={i} className="evidence-item">
                    {ev}
                  </li>
                ))}
              </ul>
            </div>

            {/* Risk Considerations */}
            {item.risk_considerations && item.risk_considerations.length > 0 && (
              <div style={{ marginBottom: "10px" }}>
                <div style={{ fontSize: "0.8rem", color: "var(--accent-amber)", fontWeight: 600 }}>
                  ⚠️ Modernization Considerations & Risks:
                </div>
                <ul style={{ paddingLeft: "18px", fontSize: "0.85rem", color: "var(--text-secondary)", marginTop: "4px" }}>
                  {item.risk_considerations.map((r, i) => (
                    <li key={i}>{r}</li>
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
