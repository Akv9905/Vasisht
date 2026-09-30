import React, { useEffect, useState } from "react";
import { Navigation, PageId } from "./components/Navigation";
import { DashboardPage } from "./pages/DashboardPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { ArchitecturePage } from "./pages/ArchitecturePage";
import { CodebasePage } from "./pages/CodebasePage";
import { DependenciesPage } from "./pages/DependenciesPage";
import { AskCodebasePage } from "./pages/AskCodebasePage";
import { ImpactPage } from "./pages/ImpactPage";
import { RisksPage } from "./pages/RisksPage";
import { ModernizationPage } from "./pages/ModernizationPage";
import { ReportsPage } from "./pages/ReportsPage";
import { api } from "./api/client";
import { Project } from "./types";

export default function App() {
  const [currentPage, setCurrentPage] = useState<PageId>("dashboard");
  const [currentProjectId, setCurrentProjectId] = useState<number>(1);
  const [projects, setProjects] = useState<Project[]>([]);
  const [online, setOnline] = useState<boolean>(false);

  useEffect(() => {
    async function checkHealth() {
      try {
        const res = await fetch("http://localhost:8000/health");
        if (res.ok) setOnline(true);
      } catch {
        setOnline(false);
      }
      const pList = await api.getProjects();
      setProjects(pList);
      if (pList.length > 0) {
        setCurrentProjectId(pList[0].id);
      }
    }
    checkHealth();
  }, []);

  return (
    <div className="app-container">
      <Navigation
        currentPage={currentPage}
        onSelectPage={(p) => setCurrentPage(p)}
        online={online}
      />

      <div className="main-wrapper">
        <header className="top-bar">
          <div className="top-bar-title" style={{ textTransform: "capitalize" }}>
            {currentPage.replace("-", " ")}
          </div>

          <div className="project-selector">
            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Active Project:</span>
            <select
              value={currentProjectId}
              onChange={(e) => setCurrentProjectId(Number(e.target.value))}
            >
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} (#{p.id})
                </option>
              ))}
            </select>
          </div>
        </header>

        <main className="content-area">
          {currentPage === "dashboard" && <DashboardPage projectId={currentProjectId} />}
          {currentPage === "projects" && (
            <ProjectsPage
              currentProjectId={currentProjectId}
              onSelectProject={(id) => setCurrentProjectId(id)}
            />
          )}
          {currentPage === "architecture" && <ArchitecturePage projectId={currentProjectId} />}
          {currentPage === "codebase" && <CodebasePage projectId={currentProjectId} />}
          {currentPage === "dependencies" && <DependenciesPage projectId={currentProjectId} />}
          {currentPage === "ask" && <AskCodebasePage projectId={currentProjectId} />}
          {currentPage === "impact" && <ImpactPage projectId={currentProjectId} />}
          {currentPage === "risks" && <RisksPage projectId={currentProjectId} />}
          {currentPage === "modernization" && <ModernizationPage projectId={currentProjectId} />}
          {currentPage === "reports" && <ReportsPage projectId={currentProjectId} />}
        </main>
      </div>
    </div>
  );
}
