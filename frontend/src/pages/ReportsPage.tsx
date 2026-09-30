import React, { useState } from "react";
import { api } from "../api/client";

interface ReportsProps {
  projectId: number;
}

export const ReportsPage: React.FC<ReportsProps> = ({ projectId }) => {
  const [format, setFormat] = useState<"markdown" | "json">("markdown");
  const [reportText, setReportText] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleGenerate = async (fmt: "markdown" | "json") => {
    setFormat(fmt);
    setLoading(true);
    const data = await api.generateReport(projectId, fmt);
    if (fmt === "json") {
      setReportText(JSON.stringify(data.content, null, 2));
    } else {
      setReportText(data.content);
    }
    setLoading(false);
  };

  return (
    <div>
      <div style={{ marginBottom: "20px" }}>
        <h2 style={{ fontSize: "1.4rem", fontWeight: 700 }}>Architecture & Intelligence Reports</h2>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.88rem" }}>
          Generate structured 11-section reports containing executive summary, inventory, architecture, request flows, risks, impact, and modernization.
        </p>
      </div>

      <div className="card">
        <div className="card-title">Generate Report</div>
        <div style={{ display: "flex", gap: "10px" }}>
          <button
            className="btn-primary"
            onClick={() => handleGenerate("markdown")}
            disabled={loading}
          >
            {loading && format === "markdown" ? "Generating..." : "📄 Generate Markdown Report"}
          </button>
          <button
            className="btn-secondary"
            onClick={() => handleGenerate("json")}
            disabled={loading}
          >
            {loading && format === "json" ? "Generating..." : "{ } Generate JSON Report"}
          </button>
        </div>
      </div>

      {reportText && (
        <div className="card">
          <div className="card-title">
            <span>Report Output ({format.toUpperCase()})</span>
            <button
              className="badge btn-secondary"
              style={{ cursor: "pointer" }}
              onClick={() => {
                navigator.clipboard.writeText(reportText);
                alert("Report copied to clipboard!");
              }}
            >
              📋 Copy to Clipboard
            </button>
          </div>

          <pre
            className="mono"
            style={{
              background: "var(--bg-secondary)",
              padding: "16px",
              borderRadius: "var(--radius-sm)",
              overflowX: "auto",
              fontSize: "0.82rem",
              lineHeight: 1.6,
              color: "#e2e8f0",
              maxHeight: "600px",
              whiteSpace: "pre-wrap",
            }}
          >
            {reportText}
          </pre>
        </div>
      )}
    </div>
  );
};
