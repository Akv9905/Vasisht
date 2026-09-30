import React, { useState } from "react";
import { GraphData, GraphNodeData } from "../types";

interface GraphProps {
  data: GraphData;
  onSelectNode?: (node: GraphNodeData) => void;
}

const CATEGORY_COLORS: Record<string, string> = {
  api: "#06b6d4",
  controller: "#3b82f6",
  service: "#8b5cf6",
  repository: "#10b981",
  database: "#f59e0b",
  test: "#ec4899",
  package: "#64748b",
  external: "#14b8a6",
  other: "#94a3b8",
};

export const InteractiveGraph: React.FC<GraphProps> = ({ data, onSelectNode }) => {
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<GraphNodeData | null>(null);

  const filteredNodes = selectedCategory
    ? data.nodes.filter((n) => n.category === selectedCategory)
    : data.nodes;

  const nodeMap = new Map<string, { x: number; y: number; node: GraphNodeData }>();

  // Circular layout positioning
  const width = 740;
  const height = 480;
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.38;

  filteredNodes.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / Math.max(1, filteredNodes.length);
    const x = cx + radius * Math.cos(angle);
    const y = cy + radius * Math.sin(angle);
    nodeMap.set(node.id, { x, y, node });
  });

  const categories = Object.keys(data.categories || {});

  return (
    <div>
      {/* Category filters */}
      <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "16px" }}>
        <button
          className={`badge ${selectedCategory === null ? "badge-verified" : "btn-secondary"}`}
          style={{ cursor: "pointer" }}
          onClick={() => setSelectedCategory(null)}
        >
          All ({data.total_nodes})
        </button>
        {categories.map((cat) => (
          <button
            key={cat}
            className={`badge ${selectedCategory === cat ? "badge-verified" : "btn-secondary"}`}
            style={{
              cursor: "pointer",
              borderColor: CATEGORY_COLORS[cat] || "#64748b",
              color: selectedCategory === cat ? "#fff" : CATEGORY_COLORS[cat] || "#cbd5e1",
            }}
            onClick={() => setSelectedCategory(selectedCategory === cat ? null : cat)}
          >
            {cat} ({data.categories[cat]})
          </button>
        ))}
      </div>

      <div style={{ position: "relative", background: "var(--bg-secondary)", borderRadius: "var(--radius-md)", border: "1px solid var(--border-subtle)", overflow: "hidden" }}>
        <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`}>
          <defs>
            <marker
              id="arrow"
              viewBox="0 0 10 10"
              refX="18"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#475569" />
            </marker>
          </defs>

          {/* Edges */}
          {data.edges.map((edge, idx) => {
            const src = nodeMap.get(edge.source);
            const tgt = nodeMap.get(edge.target);
            if (!src || !tgt) return null;

            return (
              <g key={`edge-${idx}`}>
                <line
                  x1={src.x}
                  y1={src.y}
                  x2={tgt.x}
                  y2={tgt.y}
                  stroke="#334155"
                  strokeWidth="1.5"
                  markerEnd="url(#arrow)"
                />
              </g>
            );
          })}

          {/* Nodes */}
          {filteredNodes.map((n) => {
            const pos = nodeMap.get(n.id);
            if (!pos) return null;
            const color = CATEGORY_COLORS[n.category] || "#94a3b8";
            const isHovered = hoveredNode?.id === n.id;

            return (
              <g
                key={n.id}
                transform={`translate(${pos.x}, ${pos.y})`}
                style={{ cursor: "pointer" }}
                onMouseEnter={() => setHoveredNode(n)}
                onMouseLeave={() => setHoveredNode(null)}
                onClick={() => onSelectNode && onSelectNode(n)}
              >
                <circle
                  r={isHovered ? 14 : 10}
                  fill={color}
                  stroke="#0f172a"
                  strokeWidth="2"
                  style={{ transition: "all 0.15s ease" }}
                />
                <text
                  y={isHovered ? 26 : 22}
                  textAnchor="middle"
                  fill="#f1f5f9"
                  fontSize={isHovered ? "11px" : "10px"}
                  fontWeight={isHovered ? "bold" : "normal"}
                  fontFamily="var(--font-sans)"
                >
                  {n.label.length > 20 ? n.label.substring(0, 18) + "..." : n.label}
                </text>
              </g>
            );
          })}
        </svg>

        {/* Hover info overlay */}
        {hoveredNode && (
          <div
            style={{
              position: "absolute",
              bottom: "12px",
              left: "12px",
              background: "rgba(15, 23, 42, 0.95)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-sm)",
              padding: "10px 14px",
              pointerEvents: "none",
            }}
          >
            <div style={{ fontWeight: 600, color: CATEGORY_COLORS[hoveredNode.category] || "#fff" }}>
              {hoveredNode.label}
            </div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
              Kind: {hoveredNode.kind} | Category: {hoveredNode.category}
            </div>
            {hoveredNode.file_path && (
              <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "4px" }}>
                {hoveredNode.file_path}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
