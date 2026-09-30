import React from "react";

export type PageId =
  | "dashboard"
  | "projects"
  | "architecture"
  | "codebase"
  | "dependencies"
  | "ask"
  | "impact"
  | "risks"
  | "modernization"
  | "reports";

interface NavProps {
  currentPage: PageId;
  onSelectPage: (page: PageId) => void;
  online: boolean;
}

const NAV_ITEMS: Array<{ id: PageId; label: string; icon: string }> = [
  { id: "dashboard", label: "Dashboard", icon: "📊" },
  { id: "projects", label: "Projects", icon: "📁" },
  { id: "architecture", label: "Architecture", icon: "🏛️" },
  { id: "codebase", label: "Codebase", icon: "💻" },
  { id: "dependencies", label: "Dependencies", icon: "🔗" },
  { id: "ask", label: "Ask Codebase", icon: "💬" },
  { id: "impact", label: "Impact Analysis", icon: "💥" },
  { id: "risks", label: "Risks", icon: "⚠️" },
  { id: "modernization", label: "Modernization", icon: "🚀" },
  { id: "reports", label: "Reports", icon: "📄" },
];

export const Navigation: React.FC<NavProps> = ({ currentPage, onSelectPage, online }) => {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="brand-title">
          <span>🧠</span> Enterprise AI
        </div>
        <div className="brand-subtitle">Software Intelligence Platform</div>
      </div>

      <ul className="nav-links">
        {NAV_ITEMS.map((item) => (
          <li key={item.id} className="nav-item">
            <button
              className={currentPage === item.id ? "active" : ""}
              onClick={() => onSelectPage(item.id)}
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </button>
          </li>
        ))}
      </ul>

      <div className="sidebar-footer">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <span>Engine Status</span>
          <span className="status-badge">
            <span className="status-dot"></span>
            {online ? "Online" : "Local-First"}
          </span>
        </div>
        <div>Zero-cost / deterministic</div>
      </div>
    </aside>
  );
};
