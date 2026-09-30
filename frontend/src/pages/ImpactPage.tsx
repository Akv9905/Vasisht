import React, { useState } from "react";
import { api } from "../api/client";
import { ImpactResult } from "../types";

interface ImpactProps {
  projectId: number;
}

const SAMPLE_TARGETS = [
  "PaymentService.processPayment",
  "PaymentController",
  "PaymentRepository",
  "NotificationService",
];

export const ImpactPage: React.FC<ImpactProps> = ({ projectId }) => {
  const [target, setTarget] = useState("PaymentService.processPayment");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ImpactResult | null>(null);

  const handleAnalyze = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!target.trim()) return;

    setLoading(true);
    const data = await api.analyzeImpact(projectId, target.trim());
    setResult(data);
    setLoading(false);
  };

  return (
    <div>
      <div style={{ marginBottom: "20px" }}>
        <h2 style={{ fontSize: "1.4rem", fontWeight: 700 }}>Change Impact Analysis</h2>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.88rem" }}>
          Bounded graph traversal identifying potentially affected callers, controllers, APIs, databases, and tests.
        </p>
      </div>

      <div className="card">
        <form onSubmit={handleAnalyze} className="input-group">
          <input
            type="text"
            className="text-input mono"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder="Enter class or method symbol (e.g. PaymentService.processPayment)..."
          />
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? "Tracing..." : "Analyze Impact"}
          </button>
        </form>

        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
          <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Target Symbols:</span>
          {SAMPLE_TARGETS.map((t, i) => (
            <button
              key={i}
              className="badge btn-secondary mono"
              style={{ cursor: "pointer" }}
              onClick={() => setTarget(t)}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {result && (
        <div>
          {/* Target Banner */}
          <div className="card" style={{ borderLeft: "4px solid var(--accent-rose)" }}>
            <div className="card-title">
              <span>Target: <span className="mono" style={{ color: "var(--accent-rose)" }}>{result.target}</span> ({result.target_kind})</span>
              <span className="badge badge-high">Blast Radius</span>
            </div>
            {result.target_file && (
              <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
                Source: <span className="mono">{result.target_file}</span>
              </p>
            )}
          </div>

          {/* Breakdown Grid */}
          <div className="metrics-grid">
            <div className="metric-card">
              <span className="metric-title">Directly Affected</span>
              <span className="metric-value">{result.direct_impact.length}</span>
              <span className="metric-desc">Depth 1 callers & dependents</span>
            </div>
            <div className="metric-card">
              <span className="metric-title">Indirectly Affected</span>
              <span className="metric-value">{result.indirect_impact.length}</span>
              <span className="metric-desc">Depth &gt; 1 transitive callers</span>
            </div>
            <div className="metric-card">
              <span className="metric-title">Affected APIs</span>
              <span className="metric-value">{result.affected_apis.length}</span>
              <span className="metric-desc">Exposed HTTP endpoints</span>
            </div>
            <div className="metric-card">
              <span className="metric-title">Database Objects</span>
              <span className="metric-value">{result.affected_database_objects.length}</span>
              <span className="metric-desc">Downstream tables / entities</span>
            </div>
            <div className="metric-card">
              <span className="metric-title">Affected Tests</span>
              <span className="metric-value">{result.affected_tests.length}</span>
              <span className="metric-desc">Automated test suites</span>
            </div>
          </div>

          {/* Directly Affected Table */}
          <div className="card">
            <div className="card-title">Directly Affected Callers & Dependents</div>
            {result.direct_impact.length === 0 ? (
              <p style={{ color: "var(--text-muted)", fontSize: "0.88rem" }}>No direct callers identified in call graph.</p>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Kind</th>
                    <th>Relationship</th>
                    <th>Source File</th>
                  </tr>
                </thead>
                <tbody>
                  {result.direct_impact.map((item, idx) => (
                    <tr key={idx}>
                      <td><strong>{item.name}</strong></td>
                      <td><span className="badge badge-low">{item.kind}</span></td>
                      <td><span className="mono">{item.relationship || "CALLS"}</span></td>
                      <td className="mono" style={{ fontSize: "0.8rem" }}>{item.file_path || "N/A"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Downstream Database Objects */}
          {result.affected_database_objects.length > 0 && (
            <div className="card">
              <div className="card-title">Potentially Affected Database Objects</div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Table / Entity</th>
                    <th>Kind</th>
                    <th>Relationship</th>
                  </tr>
                </thead>
                <tbody>
                  {result.affected_database_objects.map((db, idx) => (
                    <tr key={idx}>
                      <td className="mono" style={{ color: "var(--accent-amber)" }}>{db.name}</td>
                      <td>{db.kind}</td>
                      <td><span className="badge badge-medium">{db.relationship || "QUERIES"}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Affected Tests */}
          {result.affected_tests.length > 0 && (
            <div className="card">
              <div className="card-title">Affected Automated Tests</div>
              <ul className="evidence-list">
                {result.affected_tests.map((t, idx) => (
                  <li key={idx} className="evidence-item">
                    🧪 <strong>{t.name}</strong> {t.file_path ? `(${t.file_path})` : ""}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Limitations */}
          {result.limitations.length > 0 && (
            <div className="card">
              <div className="card-title" style={{ color: "var(--accent-amber)" }}>
                Impact Analysis Limitations
              </div>
              <ul style={{ paddingLeft: "20px", color: "var(--text-secondary)", fontSize: "0.85rem" }}>
                {result.limitations.map((lim, idx) => (
                  <li key={idx} style={{ marginBottom: "4px" }}>
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
