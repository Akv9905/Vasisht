import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import App from "./App";

describe("Frontend Dashboard Application (P18)", () => {
  it("renders navigation with all 10 required pages", () => {
    render(<App />);

    expect(screen.getByText("Dashboard")).toBeDefined();
    expect(screen.getByText("Projects")).toBeDefined();
    expect(screen.getByText("Architecture")).toBeDefined();
    expect(screen.getByText("Codebase")).toBeDefined();
    expect(screen.getByText("Dependencies")).toBeDefined();
    expect(screen.getByText("Ask Codebase")).toBeDefined();
    expect(screen.getByText("Impact Analysis")).toBeDefined();
    expect(screen.getByText("Risks")).toBeDefined();
    expect(screen.getByText("Modernization")).toBeDefined();
    expect(screen.getByText("Reports")).toBeDefined();
  });

  it("navigates to Ask Codebase page and shows question input", async () => {
    render(<App />);
    const askNavBtn = screen.getByText("Ask Codebase");
    fireEvent.click(askNavBtn);

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Ask a question/i)).toBeDefined();
      expect(screen.getByRole("button", { name: "Ask" })).toBeDefined();
    });
  });

  it("navigates to Impact Analysis page and shows symbol input", async () => {
    render(<App />);
    const impactNavBtn = screen.getByText("Impact Analysis");
    fireEvent.click(impactNavBtn);

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Enter class or method symbol/i)).toBeDefined();
      expect(screen.getByRole("button", { name: "Analyze Impact" })).toBeDefined();
    });
  });

  it("navigates to Risks page and displays measurable categories", async () => {
    render(<App />);
    const risksNavBtn = screen.getByText("Risks");
    fireEvent.click(risksNavBtn);

    await waitFor(() => {
      expect(screen.getByText("Technical Risk Analysis")).toBeDefined();
    });
  });

  it("navigates to Modernization page and displays candidates", async () => {
    render(<App />);
    const modNavBtn = screen.getByText("Modernization");
    fireEvent.click(modNavBtn);

    await waitFor(() => {
      expect(screen.getByText("Evidence-Backed Modernization")).toBeDefined();
    });
  });

  it("navigates to Reports page and shows format buttons", async () => {
    render(<App />);
    const repNavBtn = screen.getByText("Reports");
    fireEvent.click(repNavBtn);

    await waitFor(() => {
      expect(screen.getByText(/Generate Markdown Report/i)).toBeDefined();
      expect(screen.getByText(/Generate JSON Report/i)).toBeDefined();
    });
  });
});
