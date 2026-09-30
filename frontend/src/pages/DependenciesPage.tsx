import React, { useEffect, useState } from "react";
import { api } from "../api/client";
import { GraphData } from "../types";

interface DepProps {
  projectId: number;
}

export const DependenciesPage: React.FC<DepProps> = ({ projectId }) => {
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      const data = await api.getGraph(projectId);
      setGraph(data);
      setLoading(false);
    }
    load();
  }, [projectId]);

  if (loading || !graph) {
    return <div className="card">Loading dependency relationships...</div>;
  }

  return (
    <div>
      <div style={{ marginBottom: "20px" }}>
        <h2 style={{ fontSize: "1.4rem", fontWeight: 700 }}>Software Dependencies</h2>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.88rem" }}>
          Explore caller-callee hierarchies, class dependencies, framework exposures, and database queries.
        </p>
      </div>

      <div className="metrics-grid">
        <div className="metric-card">
          <span className="metric-title">Total Nodes</span>
          <span className="metric-value">{graph.total_nodes}</span>
        </div>
        <div className="metric-card">
          <span className="metric-title">Total Edges</span>
          <span className="metric-value">{graph.total_edges}</span>
        </div>
        <div className="metric-card">
          <span className="metric-title">Resolved</span>
          <span className="metric-value">{graph.edges.filter((e) => e.resolved).length}</span>
        </div>
        <div className="metric-card">
          <span className="metric-title">Categories</span>
          <span className="metric-value">{Object.keys(graph.categories).length}</span>
        </div>
      </div>

      <div className="card">
        <div className="card-title">Graph Relationship Table</div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Source Symbol</th>
              <th>Relationship</th>
              <th>Target Symbol</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {graph.edges.map((e, idx) => (
              <tr key={idx}>
                <td className="mono">{e.source}</td>
                <td>
                  <span className="badge badge-low">{e.relationship}</span>
                </td>
                <td className="mono">{e.target}</td>
                <td>
                  <span className={`badge ${e.resolved ? "badge-verified" : "badge-medium"}`}>
                    {e.resolved ? "Resolved" : "Unresolved"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
