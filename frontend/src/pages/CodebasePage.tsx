import React, { useEffect, useState } from "react";
import { api } from "../api/client";
import { ClassItem, FileItem, MethodItem } from "../types";

interface CodebaseProps {
  projectId: number;
}

export const CodebasePage: React.FC<CodebaseProps> = ({ projectId }) => {
  const [tab, setTab] = useState<"classes" | "methods" | "files">("classes");
  const [classes, setClasses] = useState<ClassItem[]>([]);
  const [methods, setMethods] = useState<MethodItem[]>([]);
  const [files, setFiles] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setLoading(true);
      const [clsData, mthData, fData] = await Promise.all([
        api.getClasses(projectId),
        api.getMethods(projectId),
        api.getFiles(projectId),
      ]);
      setClasses(clsData);
      setMethods(mthData);
      setFiles(fData);
      setLoading(false);
    }
    load();
  }, [projectId]);

  return (
    <div>
      <div style={{ marginBottom: "20px" }}>
        <h2 style={{ fontSize: "1.4rem", fontWeight: 700 }}>Codebase Inventory</h2>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.88rem" }}>
          Inspect actual extracted classes, methods, signatures, annotations, and compilation units.
        </p>
      </div>

      <div style={{ display: "flex", gap: "10px", marginBottom: "20px" }}>
        <button
          className={tab === "classes" ? "btn-primary" : "btn-secondary"}
          onClick={() => setTab("classes")}
        >
          Classes & Interfaces ({classes.length})
        </button>
        <button
          className={tab === "methods" ? "btn-primary" : "btn-secondary"}
          onClick={() => setTab("methods")}
        >
          Methods & Signatures ({methods.length})
        </button>
        <button
          className={tab === "files" ? "btn-primary" : "btn-secondary"}
          onClick={() => setTab("files")}
        >
          Files ({files.length})
        </button>
      </div>

      {loading ? (
        <div className="card">Loading inventory...</div>
      ) : tab === "classes" ? (
        <div className="card">
          <table className="data-table">
            <thead>
              <tr>
                <th>Class Name</th>
                <th>Kind</th>
                <th>Qualified Name</th>
                <th>Span (Lines)</th>
                <th>Annotations</th>
              </tr>
            </thead>
            <tbody>
              {classes.map((c) => (
                <tr key={c.id}>
                  <td><strong>{c.name}</strong></td>
                  <td><span className="badge badge-low">{c.kind}</span></td>
                  <td className="mono">{c.qualified_name}</td>
                  <td className="mono">
                    {c.start_line && c.end_line ? `L${c.start_line} - L${c.end_line}` : "N/A"}
                  </td>
                  <td>
                    {c.annotations.map((a, i) => (
                      <span key={i} className="badge badge-medium" style={{ marginRight: 4 }}>
                        @{a.name}
                      </span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : tab === "methods" ? (
        <div className="card">
          <table className="data-table">
            <thead>
              <tr>
                <th>Method Name</th>
                <th>Signature</th>
                <th>Return Type</th>
                <th>Lines</th>
              </tr>
            </thead>
            <tbody>
              {methods.map((m) => (
                <tr key={m.id}>
                  <td><strong>{m.name}</strong></td>
                  <td className="mono" style={{ color: "var(--accent-cyan)" }}>{m.signature}</td>
                  <td><span className="mono">{m.return_type || "void"}</span></td>
                  <td className="mono">
                    {m.start_line && m.end_line ? `L${m.start_line}-${m.end_line}` : "N/A"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="card">
          <table className="data-table">
            <thead>
              <tr>
                <th>Relative Path</th>
                <th>Size (Bytes)</th>
                <th>Categories</th>
              </tr>
            </thead>
            <tbody>
              {files.map((f) => (
                <tr key={f.id}>
                  <td className="mono">{f.relative_path}</td>
                  <td>{f.size_bytes} B</td>
                  <td>
                    {f.categories.map((cat, i) => (
                      <span key={i} className="badge badge-low" style={{ marginRight: 4 }}>
                        {cat}
                      </span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
