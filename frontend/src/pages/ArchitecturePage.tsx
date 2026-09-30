import React, { useEffect, useState } from "react";
import { api } from "../api/client";
import { InteractiveGraph } from "../components/InteractiveGraph";
import { ArchitectureData, GraphData, GraphNodeData } from "../types";

interface ArchProps {
  projectId: number;
}

export const ArchitecturePage: React.FC<ArchProps> = ({ projectId }) => {
  const [arch, setArch] = useState<ArchitectureData | null>(null);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNodeData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setLoading(true);
      const [archData, graphData] = await Promise.all([
        api.getArchitecture(projectId),
        api.getGraph(projectId),
      ]);
      setArch(archData);
      setGraph(graphData);
      setLoading(false);
    }
    load();
  }, [projectId]);

  if (loading || !arch || !graph) {
    return <div className="card">Loading architecture graph...</div>;
  }

  return (
    <div>
      <div style={{ marginBottom: "20px" }}>
        <h2 style={{ fontSize: "1.4rem", fontWeight: 700 }}>Architecture Visualization</h2>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.88rem" }}>
          Interactive software dependency graph representing packages, controllers, services, repositories, databases, APIs, and tests.
        </p>
      </div>

      {/* Interactive Visualizer */}
      <div className="card">
        <div className="card-title">
          <span>Interactive Component Graph</span>
          <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
            Click node to view details • Filter by category above
          </span>
        </div>
        <InteractiveGraph data={graph} onSelectNode={(n) => setSelectedNode(n)} />
      </div>

      {selectedNode && (
        <div className="card" style={{ borderLeft: "4px solid var(--accent-blue)" }}>
          <div className="card-title">Selected Node Details</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", fontSize: "0.88rem" }}>
            <div><strong>Symbol ID:</strong> <span className="mono">{selectedNode.id}</span></div>
            <div><strong>Label:</strong> {selectedNode.label}</div>
            <div><strong>Kind:</strong> {selectedNode.kind}</div>
            <div><strong>Category:</strong> {selectedNode.category}</div>
            {selectedNode.file_path && (
              <div style={{ gridColumn: "span 2" }}>
                <strong>File Path:</strong> <span className="mono">{selectedNode.file_path}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Structured Architecture Breakdown */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>
        <div className="card">
          <div className="card-title">Controllers & Endpoints</div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Controller</th>
                <th>Endpoints</th>
              </tr>
            </thead>
            <tbody>
              {arch.controllers.map((c, i) => (
                <tr key={i}>
                  <td><strong>{c.name}</strong></td>
                  <td>{c.endpoints.join(", ") || "None"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card">
          <div className="card-title">Services & Repositories</div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Service</th>
                <th>Injected Repositories</th>
              </tr>
            </thead>
            <tbody>
              {arch.services.map((s, i) => (
                <tr key={i}>
                  <td><strong>{s.name}</strong></td>
                  <td>{s.repositories_used.join(", ") || "Domain Service"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
