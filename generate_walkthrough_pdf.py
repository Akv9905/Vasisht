"""
Enterprise AI Platform Walkthrough PDF Generator
Generates a publication-quality, 5-page technical walkthrough PDF for
the Enterprise AI Legacy Software Intelligence & Modernization Platform (Phases P0-P22).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
)
from reportlab.pdfgen import canvas

PAGE_WIDTH, PAGE_HEIGHT = letter  # 612 x 792 pt
MARGIN = 40  # Printable width = 612 - 80 = 532 pt

NAVY = colors.HexColor("#0F172A")
SLATE_DARK = colors.HexColor("#1E293B")
SLATE_MED = colors.HexColor("#475569")
SLATE_LIGHT = colors.HexColor("#F8FAFC")
BLUE_ACCENT = colors.HexColor("#2563EB")
BLUE_BG = colors.HexColor("#EFF6FF")
TEAL_ACCENT = colors.HexColor("#0D9488")
TEAL_BG = colors.HexColor("#F0FDFA")
BORDER_COLOR = colors.HexColor("#E2E8F0")
BORDER_DARK = colors.HexColor("#CBD5E1")
TEXT_MAIN = colors.HexColor("#1E293B")
TEXT_MUTED = colors.HexColor("#64748B")
GREEN_ACCENT = colors.HexColor("#16A34A")
GREEN_BG = colors.HexColor("#F0FDF4")
ORANGE_ACCENT = colors.HexColor("#D97706")
ORANGE_BG = colors.HexColor("#FFFBEB")
RED_ACCENT = colors.HexColor("#DC2626")


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas for dynamic total page counting and running headers/footers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_decorations(self, total_pages):
        self.saveState()
        self.setFont("Helvetica", 7.5)
        self.setFillColor(TEXT_MUTED)

        if self._pageNumber > 1:
            # Running Header
            self.drawString(MARGIN, PAGE_HEIGHT - 28, "Enterprise AI | Legacy Software Intelligence & Modernization Platform")
            self.drawRightString(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 28, "Technical Walkthrough (Phases P0 - P22)")
            self.setStrokeColor(BORDER_COLOR)
            self.setLineWidth(0.5)
            self.line(MARGIN, PAGE_HEIGHT - 32, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 32)

        # Running Footer (on all pages)
        self.setStrokeColor(BORDER_COLOR)
        self.setLineWidth(0.5)
        self.line(MARGIN, 32, PAGE_WIDTH - MARGIN, 32)
        self.drawString(MARGIN, 22, "Confidential & Proprietary | Deterministic Software Intelligence -- Zero Paid API Architecture")
        page_text = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(PAGE_WIDTH - MARGIN, 22, page_text)

        self.restoreState()


def create_styles():
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="DocTitle",
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=23,
        textColor=NAVY,
        spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        name="DocSubTitle",
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=BLUE_ACCENT,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="SectionH1",
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=NAVY,
        spaceBefore=7,
        spaceAfter=4,
        keepWithNext=True,
    ))
    styles.add(ParagraphStyle(
        name="SectionH2",
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=12.5,
        textColor=SLATE_DARK,
        spaceBefore=5,
        spaceAfter=3,
        keepWithNext=True,
    ))
    styles.add(ParagraphStyle(
        name="SectionH3",
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=BLUE_ACCENT,
        spaceBefore=4,
        spaceAfter=2,
        keepWithNext=True,
    ))
    styles.add(ParagraphStyle(
        name="CustomBody",
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=TEXT_MAIN,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="BulletItem",
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        textColor=TEXT_MAIN,
        leftIndent=8,
        spaceAfter=2.5,
    ))
    styles.add(ParagraphStyle(
        name="CodeBlock",
        fontName="Courier",
        fontSize=7,
        leading=9,
        textColor=SLATE_DARK,
        spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        name="TableHead",
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.white,
    ))
    styles.add(ParagraphStyle(
        name="TableCell",
        fontName="Helvetica",
        fontSize=7.2,
        leading=9.2,
        textColor=TEXT_MAIN,
    ))
    styles.add(ParagraphStyle(
        name="TableCellBold",
        fontName="Helvetica-Bold",
        fontSize=7.2,
        leading=9.2,
        textColor=TEXT_MAIN,
    ))
    styles.add(ParagraphStyle(
        name="TableCellCategory",
        fontName="Helvetica-Bold",
        fontSize=6.8,
        leading=8.8,
        textColor=TEXT_MAIN,
    ))
    styles.add(ParagraphStyle(
        name="TableCellCode",
        fontName="Courier",
        fontSize=6.8,
        leading=8.5,
        textColor=SLATE_DARK,
    ))
    styles.add(ParagraphStyle(
        name="CalloutText",
        fontName="Helvetica",
        fontSize=7.8,
        leading=10.5,
        textColor=SLATE_DARK,
    ))
    return styles


def callout_box(text: str, title: str = "KEY ARCHITECTURAL INVARIANT", border_color=BLUE_ACCENT, bg_color=BLUE_BG, styles=None):
    p_title = Paragraph(f"<b>{title}</b>", styles["SectionH3"] if styles else getSampleStyleSheet()["Normal"])
    p_text = Paragraph(text, styles["CalloutText"] if styles else getSampleStyleSheet()["Normal"])
    table_data = [[p_title], [p_text]]
    box = Table(table_data, colWidths=[532])
    box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg_color),
        ('BOX', (0, 0), (-1, -1), 0.75, border_color),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, border_color),
    ]))
    return box


def code_box(code_lines: list[str], styles):
    content = "<br/>".join(line.replace(" ", "&nbsp;") for line in code_lines)
    p = Paragraph(content, styles["CodeBlock"])
    table = Table([[p]], colWidths=[532])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    return table


def build_walkthrough_pdf(output_path: str):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
    )
    styles = create_styles()
    story = []

    # =========================================================================
    # PAGE 1: TITLE, EXECUTIVE BRIEFING & CORE ARCHITECTURAL PIPELINE
    # =========================================================================
    story.append(Paragraph("Enterprise AI -- Platform Walkthrough", styles["DocTitle"]))
    story.append(Paragraph("Legacy Software Intelligence & Modernization Platform | Complete Guide (Phases P0 - P22)", styles["DocSubTitle"]))

    # Key Status Grid
    meta_data = [
        [
            Paragraph("<b>Implementation:</b> Phases P0 - P22 Complete", styles["TableCellBold"]),
            Paragraph("<b>Backend Tests:</b> 309 / 309 Passing (Pytest)", styles["TableCellBold"]),
            Paragraph("<b>Frontend Tests:</b> 6 / 6 Passing (Vitest)", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>Cost Mode:</b> 100% Deterministic (Zero Paid APIs)", styles["TableCell"]),
            Paragraph("<b>Evaluation:</b> 35 Grounded Items (0% Hallucination)", styles["TableCell"]),
            Paragraph("<b>Target Stack:</b> Java, Spring Boot, JPA, PostgreSQL", styles["TableCell"]),
        ]
    ]
    meta_table = Table(meta_data, colWidths=[177, 177, 178])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), SLATE_LIGHT),
        ('BOX', (0, 0), (-1, -1), 0.75, BORDER_DARK),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 6))

    # Executive Briefing Callout
    exec_summary_text = (
        "Enterprise AI is a production-ready legacy software intelligence platform designed specifically for "
        "Java and Spring Boot enterprise ecosystems. It provides automated codebase discovery, dependency graph "
        "extraction, end-to-end request flow tracing, change-impact blast radius computation, deterministic risk "
        "detection, and modernization planning -- operating entirely locally with zero required paid APIs or "
        "cloud dependencies. Every insight is strictly grounded in AST syntax and relational persistence models."
    )
    story.append(callout_box(exec_summary_text, "EXECUTIVE BRIEFING & SYSTEM PURPOSE", border_color=BLUE_ACCENT, bg_color=BLUE_BG, styles=styles))
    story.append(Spacer(1, 6))

    # Core Principles Callout
    principles_text = (
        "<b>1. Zero Code Invention:</b> The system never invents classes, methods, endpoints, or dependencies.<br/>"
        "<b>2. Deterministic Grounding:</b> AST parser and SQL persistence are the single source of truth.<br/>"
        "<b>3. Evidence-First Synthesis:</b> Answers must cite exact source files, line numbers, and relationships.<br/>"
        "<b>4. Complete Privacy:</b> Source code is never transmitted to external third-party LLM providers."
    )
    story.append(callout_box(principles_text, "CORE ARCHITECTURAL INVARIANTS", border_color=TEAL_ACCENT, bg_color=TEAL_BG, styles=styles))
    story.append(Spacer(1, 8))

    # Section 1: End-to-End Pipeline Table
    story.append(Paragraph("1. End-to-End Architectural Pipeline", styles["SectionH1"]))
    pipeline_rows = [
        [
            Paragraph("<b>Stage</b>", styles["TableHead"]),
            Paragraph("<b>Module</b>", styles["TableHead"]),
            Paragraph("<b>Technical Responsibility & Guarantees</b>", styles["TableHead"]),
            Paragraph("<b>Determinism</b>", styles["TableHead"]),
        ],
        [
            Paragraph("<b>1. Ingestion</b>", styles["TableCellBold"]),
            Paragraph("Safe Scanner / ZIP Reader", styles["TableCell"]),
            Paragraph("Directory & ZIP scanning. Blocks path traversal attacks (Zip-Slip) using canonical path validation. Discovers Java, SQL, config, and docs.", styles["TableCell"]),
            Paragraph("100% Deterministic", styles["TableCell"]),
        ],
        [
            Paragraph("<b>2. AST Parsing</b>", styles["TableCellBold"]),
            Paragraph("Java AST & Annotation Engine", styles["TableCell"]),
            Paragraph("Extracts packages, classes, interfaces, methods, constructors, fields, Spring REST endpoints (@GetMapping, @PostMapping), and database entities.", styles["TableCell"]),
            Paragraph("100% Deterministic", styles["TableCell"]),
        ],
        [
            Paragraph("<b>3. Graph Synth</b>", styles["TableCellBold"]),
            Paragraph("Dependency Graph Extractor", styles["TableCell"]),
            Paragraph("Builds typed directed graph across 11 edge types (CALLS, IMPORTS, EXTENDS, QUERIES, EXPOSES, etc.). Preserves and reports unresolved calls.", styles["TableCell"]),
            Paragraph("100% Deterministic", styles["TableCell"]),
        ],
        [
            Paragraph("<b>4. Persistence</b>", styles["TableCellBold"]),
            Paragraph("PostgreSQL / Alembic Store", styles["TableCell"]),
            Paragraph("Stores immutable historical snapshots across 21 relational tables. Supports historical diffs, symbol searches, and graph queries.", styles["TableCell"]),
            Paragraph("100% Deterministic", styles["TableCell"]),
        ],
        [
            Paragraph("<b>5. Graph Engine</b>", styles["TableCellBold"]),
            Paragraph("Knowledge Graph Traversal", styles["TableCell"]),
            Paragraph("Executes bounded BFS/DFS traversals, shortest path calculations, request flow tracing, and Controller -> Service -> Repo architecture validation.", styles["TableCell"]),
            Paragraph("100% Deterministic", styles["TableCell"]),
        ],
        [
            Paragraph("<b>6. Retrieval</b>", styles["TableCellBold"]),
            Paragraph("Structured & Semantic Layer", styles["TableCell"]),
            Paragraph("Structured symbol lookup + local embeddings fallback. Packages exact file:line source evidence cards for human and machine inspection.", styles["TableCell"]),
            Paragraph("100% Deterministic", styles["TableCell"]),
        ],
        [
            Paragraph("<b>7. Presentation</b>", styles["TableCellBold"]),
            Paragraph("CLI, FastAPI & React App", styles["TableCell"]),
            Paragraph("13-command CLI, 15+ REST endpoints, and a 10-page React dashboard delivering interactive flow graphs, blast radius trees, and executive reports.", styles["TableCell"]),
            Paragraph("Zero Hallucination", styles["TableCell"]),
        ],
    ]
    pipeline_table = Table(pipeline_rows, colWidths=[65, 105, 274, 88])
    pipeline_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), SLATE_DARK),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, SLATE_LIGHT]),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
    ]))
    story.append(pipeline_table)

    story.append(PageBreak())

    # =========================================================================
    # PAGE 2: COMPLETE IMPLEMENTATION WALKTHROUGH (PHASES P0 - P22)
    # =========================================================================
    story.append(Paragraph("2. Complete Implementation Walkthrough (Phases P0 - P22)", styles["SectionH1"]))
    story.append(Paragraph(
        "All 23 planned phases have been engineered, integrated, and validated with automated regression suites.",
        styles["CustomBody"]
    ))

    # Phase Group A
    story.append(Paragraph("A. Ingestion, AST Parsing & Knowledge Graph (Phases P0 - P5)", styles["SectionH2"]))
    phases_a = [
        ("P0: Setup & Health Scaffolding", "Configured Python 3.11 backend with FastAPI, Pydantic, SQLAlchemy, Alembic migrations, and verified GET /health with CORS."),
        ("P1: Repository Scanner & Zip-Slip Defense", "Directory and safe ZIP ingestion. Categorizes Java, Config, SQL, and Docs. Validates against directory traversal (Zip-Slip) attacks."),
        ("P2: Java AST & Annotation Extractor", "AST parser capturing classes, interfaces, methods, constructors, fields, Spring REST endpoints (@GetMapping, @PostMapping), and JPA tables."),
        ("P3: Dependency Graph Model", "Typed directed graph across 11 relationships: CONTAINS, IMPORTS, EXTENDS, IMPLEMENTS, CALLS, USES, EXPOSES, QUERIES, DEPENDS_ON, REFERENCES, TESTS."),
        ("P4: PostgreSQL Persistence & Snapshots", "Relational persistence across 21 domain tables. Stores complete analysis snapshots, indexes graph nodes/edges, and tracks historical runs."),
        ("P5: Knowledge Graph Traversal Engine", "Graph traversal supporting direct neighbors, upstream callers, downstream callees, bounded impact traversal, and verified 4-tier architectural chains."),
    ]
    for p_title, p_desc in phases_a:
        story.append(Paragraph(f"- <b>{p_title}</b>: {p_desc}", styles["BulletItem"]))

    story.append(Spacer(1, 4))

    # Phase Group B
    story.append(Paragraph("B. CLI, Retrieval Pipeline & Evidence Synthesis (Phases P6 - P10)", styles["SectionH2"]))
    phases_b = [
        ("P6: Unified Analysis CLI", "Comprehensive command-line tool with 13 subcommands, supporting dual-syntax invocation (analyze.py <path> <cmd> or analyze.py <cmd> <path>)."),
        ("P7: Structured Symbol Retrieval", "Extracts exact symbols, callers, callees, and architectural chains using symbol tables and graph traversal without requiring AI models."),
        ("P8: Local Semantic Retrieval Fallback", "Optional local embedding engine for documentation and natural language queries, featuring automatic deterministic keyword fallback."),
        ("P9: Local LLM Provider Abstraction", "Pluggable LLM interface supporting local models (Ollama/llama3) while defaulting to zero-cost deterministic analysis if no local model is running."),
        ("P10: Evidence-Grounded Q&A Engine", "Synthesizes precise answers citing verified file:line references, request flows, and explicit disclosures of unresolved calls and limitations."),
    ]
    for p_title, p_desc in phases_b:
        story.append(Paragraph(f"- <b>{p_title}</b>: {p_desc}", styles["BulletItem"]))

    story.append(Spacer(1, 4))

    # Phase Group C
    story.append(Paragraph("C. Core Software Intelligence & Reasoning Engines (Phases P11 - P16)", styles["SectionH2"]))
    phases_c = [
        ("P11: Request Flow Tracing", "Traces full execution paths from HTTP endpoints through controllers, service orchestrators, and repositories down to physical SQL tables."),
        ("P12: Change-Impact Blast Radius", "Computes upstream callers, downstream dependencies, affected APIs, database entities, and associated test suites when a symbol changes."),
        ("P13: Measurable Technical Risk Engine", "Audits structural health: circular dependencies, high fan-out, high fan-in, unlayered database coupling, missing tests, and God classes."),
        ("P14: Architecture Visualization Data", "Generates layered architectural topology data categorizing nodes by architectural role for visual inspection in frontend graph viewers."),
        ("P15: Evidence-Backed Modernization Advisor", "Detects monolithic coupling, circular dependencies, and legacy framework patterns, ranking refactoring targets by structural dependency."),
        ("P16: Comprehensive Multi-Format Reporting", "Generates formal 11-section reports in Markdown and JSON covering executive summaries, inventory, architecture, risk matrices, and roadmaps."),
    ]
    for p_title, p_desc in phases_c:
        story.append(Paragraph(f"- <b>{p_title}</b>: {p_desc}", styles["BulletItem"]))

    story.append(Spacer(1, 4))

    # Phase Group D
    story.append(Paragraph("D. Web Application, Security & Evaluation (Phases P17 - P22)", styles["SectionH2"]))
    phases_d = [
        ("P17: Production FastAPI Endpoints", "Comprehensive REST API exposing project lifecycle, file/class browsers, graph traversal, request tracing, impact analysis, and report generation."),
        ("P18: Functional React Dashboard (10 Pages)", "Full single-page application built with React, Vite, and TypeScript featuring 10 dedicated views with real-time metrics and graph visualizers."),
        ("P19: Security Foundations", "Authentication abstraction, project tenant isolation, upload size controls, secret sanitization (redacting tokens/keys), and audit logging."),
        ("P20: Multi-Service Docker Orchestration", "Multi-stage Dockerfiles and docker-compose orchestration coordinating PostgreSQL 16, FastAPI backend, and React/Nginx frontend."),
        ("P21: 35-Item Grounded Evaluation Suite", "Formal benchmark covering 35 complex questions across 10 categories, evaluating precision, recall, and verifying 0% hallucination."),
        ("P22: Automated Test & Validation Harness", "Continuous verification suite running 309 pytest backend tests and 6 vitest frontend tests with 100% pass rate."),
    ]
    for p_title, p_desc in phases_d:
        story.append(Paragraph(f"- <b>{p_title}</b>: {p_desc}", styles["BulletItem"]))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 3: UNIFIED CLI COMMAND REFERENCE
    # =========================================================================
    story.append(Paragraph("3. Unified CLI Command Reference (13 Subcommands)", styles["SectionH1"]))
    story.append(Paragraph(
        "The CLI provides both high-level project summaries and granular symbol-level inspection. "
        "It supports dual invocation: <code>python analyzer-cli/analyze.py &lt;path&gt; &lt;command&gt;</code> or "
        "<code>python analyzer-cli/analyze.py &lt;command&gt; &lt;path&gt;</code>.",
        styles["CustomBody"]
    ))

    cli_rows = [
        [
            Paragraph("<b>Command</b>", styles["TableHead"]),
            Paragraph("<b>Key Arguments & Flags</b>", styles["TableHead"]),
            Paragraph("<b>Output & Technical Functionality</b>", styles["TableHead"]),
        ],
        [
            Paragraph("<code>analyze</code>", styles["TableCellCode"]),
            Paragraph("<code>--persist, --json, --list-files</code>", styles["TableCell"]),
            Paragraph("Default command. Scans repo, parses Java AST, extracts dependencies, validates architecture, and audits risks.", styles["TableCell"]),
        ],
        [
            Paragraph("<code>inspect</code>", styles["TableCellCode"]),
            Paragraph("<code>(none)</code>", styles["TableCell"]),
            Paragraph("Inventory summary, package hierarchy, database references, and verified architectural chains.", styles["TableCell"]),
        ],
        [
            Paragraph("<code>list-classes</code>", styles["TableCellCode"]),
            Paragraph("<code>(none)</code>", styles["TableCell"]),
            Paragraph("Enumerates all discovered classes, interfaces, records, and enums with line numbers and source file paths.", styles["TableCell"]),
        ],
        [
            Paragraph("<code>list-methods</code>", styles["TableCellCode"]),
            Paragraph("<code>(none)</code>", styles["TableCell"]),
            Paragraph("Lists all methods with return types, signatures, annotations, parameter lists, and enclosing classes.", styles["TableCell"]),
        ],
        [
            Paragraph("<code>show-class</code>", styles["TableCellCode"]),
            Paragraph("<code>&lt;ClassName&gt;</code>", styles["TableCell"]),
            Paragraph("Detailed breakdown of class annotations, fields, methods, implemented interfaces, and direct dependencies.", styles["TableCell"]),
        ],
        [
            Paragraph("<code>show-dependencies</code>", styles["TableCellCode"]),
            Paragraph("<code>[symbol]</code>", styles["TableCell"]),
            Paragraph("Displays incoming callers, outgoing callees, and overall relationship type distribution.", styles["TableCell"]),
        ],
        [
            Paragraph("<code>show-graph</code>", styles["TableCellCode"]),
            Paragraph("<code>--format dot|json</code>", styles["TableCell"]),
            Paragraph("Outputs graph topology metrics, node kind distribution, and optional Graphviz DOT/JSON representations.", styles["TableCell"]),
        ],
        [
            Paragraph("<code>trace-request</code>", styles["TableCellCode"]),
            Paragraph("<code>&lt;/api/path&gt;</code>", styles["TableCell"]),
            Paragraph("Traces sequential request flow: Endpoint -> Controller -> Service -> Repository -> Table with verification status.", styles["TableCell"]),
        ],
        [
            Paragraph("<code>impact</code>", styles["TableCellCode"]),
            Paragraph("<code>&lt;Symbol&gt; [--depth N]</code>", styles["TableCell"]),
            Paragraph("Calculates change blast radius: directly/indirectly affected classes, APIs, databases, and test suites.", styles["TableCell"]),
        ],
        [
            Paragraph("<code>risks</code>", styles["TableCellCode"]),
            Paragraph("<code>(none)</code>", styles["TableCell"]),
            Paragraph("Outputs deterministic risk findings: circular dependencies, high fan-out, missing tests, coupling hotspots.", styles["TableCell"]),
        ],
        [
            Paragraph("<code>ask</code>", styles["TableCellCode"]),
            Paragraph("<code>&quot;&lt;Question&gt;&quot;</code>", styles["TableCell"]),
            Paragraph("Evidence-backed natural language Q&A synthesizing verified code traces and explicit analysis limitations.", styles["TableCell"]),
        ],
        [
            Paragraph("<code>report</code>", styles["TableCellCode"]),
            Paragraph("<code>--format md|json --output &lt;f&gt;</code>", styles["TableCell"]),
            Paragraph("Generates an 11-section executive intelligence report in Markdown or JSON format.", styles["TableCell"]),
        ],
        [
            Paragraph("<code>architecture</code>", styles["TableCellCode"]),
            Paragraph("<code>(none)</code>", styles["TableCell"]),
            Paragraph("Displays layered architecture breakdown: Controllers, Services, Repositories, Entities, and SQL Tables.", styles["TableCell"]),
        ],
    ]
    cli_table = Table(cli_rows, colWidths=[95, 115, 322])
    cli_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), SLATE_DARK),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 2.8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.8),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, SLATE_LIGHT]),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
    ]))
    story.append(cli_table)
    story.append(Spacer(1, 8))

    # CLI Flags Summary Callout
    flags_summary = (
        "<b>Common Operational CLI Flags:</b><br/>"
        "- <code>--persist</code>: Persists analysis results as an immutable snapshot in PostgreSQL.<br/>"
        "- <code>--json</code>: Emits machine-readable JSON output for CI/CD integration.<br/>"
        "- <code>--scan-only</code>: Performs file discovery and inventory categorization without AST parsing.<br/>"
        "- <code>--project-name &lt;name&gt;</code>: Custom project label assigned to the persisted run snapshot.<br/>"
        "- <code>--list-files / --list-types</code>: Prints exhaustive file catalog or extracted type hierarchy."
    )
    story.append(callout_box(flags_summary, "CLI RUNTIME FLAGS & EXTENSIONS", border_color=BLUE_ACCENT, bg_color=BLUE_BG, styles=styles))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 4: LIVE CASE STUDY - PAYMENT-SERVICE
    # =========================================================================
    story.append(Paragraph("4. Live Case Study: payment-service Fixture", styles["SectionH1"]))
    story.append(Paragraph(
        "The platform includes a real-world Spring Boot microservice fixture (<code>sample-projects/payment-service</code>) "
        "engineered with layered REST services, JPA persistence, intentional circular dependencies, "
        "high fan-out components, and partial test coverage to validate real-world detection capabilities.",
        styles["CustomBody"]
    ))

    # Case Study Sub-section A
    story.append(Paragraph("A. Request Flow Tracing Execution", styles["SectionH2"]))
    story.append(Paragraph(
        "Executing <code>trace-request /api/payment</code> traces the complete path down to the database table:",
        styles["CustomBody"]
    ))
    flow_code = [
        "$ python analyzer-cli/analyze.py ./sample-projects/payment-service trace-request /api/payment",
        "",
        "Request Flow for: /api/payment",
        "  1. [endpoint]       POST /api/payment (src/.../controller/PaymentController.java:27)",
        "  2. [method]         create --[EXPOSES]--> (PaymentController.java)",
        "  3. [method]         processPayment --[CALLS]--> (PaymentService.java)",
        "  4. [method]         save --[CALLS]--> (PaymentRepository.java)",
        "  5. [database_table] payments --[QUERIES]--> (PaymentEntity.java)",
        "  [OK] Reaches database table: payments",
        "  Unresolved calls: String.valueOf, body.get, ResponseEntity.ok, entity.setAmount",
    ]
    story.append(code_box(flow_code, styles))
    story.append(Spacer(1, 6))

    # Case Study Sub-section B
    story.append(Paragraph("B. Deterministic Risk Findings Audit (16 Total Findings)", styles["SectionH2"]))
    story.append(Paragraph(
        "Running <code>risks</code> detected 16 measurable findings across the codebase without arbitrary AI scoring:",
        styles["CustomBody"]
    ))

    risk_findings_table = [
        [
            Paragraph("<b>Severity</b>", styles["TableHead"]),
            Paragraph("<b>Category</b>", styles["TableHead"]),
            Paragraph("<b>Component</b>", styles["TableHead"]),
            Paragraph("<b>Measurable Evidence & Architectural Impact</b>", styles["TableHead"]),
        ],
        [
            Paragraph("<font color='#DC2626'><b>HIGH</b></font>", styles["TableCell"]),
            Paragraph("CIRCULAR_DEPENDENCY", styles["TableCellCategory"]),
            Paragraph("NotificationService <-> PaymentService", styles["TableCellCode"]),
            Paragraph("Bidirectional call cycle detected: NotificationService calls PaymentService, and PaymentService calls NotificationService.", styles["TableCell"]),
        ],
        [
            Paragraph("<font color='#DC2626'><b>HIGH</b></font>", styles["TableCell"]),
            Paragraph("HIGH_COUPLING", styles["TableCellCategory"]),
            Paragraph("PaymentService", styles["TableCellCode"]),
            Paragraph("High bidirectional coupling: 8 incoming dependencies, 7 outgoing dependencies, 4 callers, 4 callees.", styles["TableCell"]),
        ],
        [
            Paragraph("<font color='#DC2626'><b>HIGH</b></font>", styles["TableCell"]),
            Paragraph("HIGH_DEPENDENCY_COMPONENT", styles["TableCellCategory"]),
            Paragraph("MetricsFacade", styles["TableCellCode"]),
            Paragraph("Central structural bottleneck: 6 incoming callers with zero downstream callees.", styles["TableCell"]),
        ],
        [
            Paragraph("<font color='#D97706'><b>MEDIUM</b></font>", styles["TableCell"]),
            Paragraph("HIGH_FAN_OUT", styles["TableCellCategory"]),
            Paragraph("RefundController", styles["TableCellCode"]),
            Paragraph("Controller has high fan-out coupling (5 outgoing dependencies).", styles["TableCell"]),
        ],
        [
            Paragraph("<font color='#D97706'><b>MEDIUM</b></font>", styles["TableCell"]),
            Paragraph("TESTING_GAP", styles["TableCellCategory"]),
            Paragraph("NotificationService", styles["TableCellCode"]),
            Paragraph("Zero automated tests reference or exercise NotificationService.", styles["TableCell"]),
        ],
        [
            Paragraph("<font color='#D97706'><b>MEDIUM</b></font>", styles["TableCell"]),
            Paragraph("DATABASE_COUPLING", styles["TableCellCategory"]),
            Paragraph("PaymentRepository", styles["TableCellCode"]),
            Paragraph("Directly binds to PaymentEntity and physical SQL table 'payments'.", styles["TableCell"]),
        ],
    ]
    risk_table = Table(risk_findings_table, colWidths=[55, 135, 110, 232])
    risk_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), SLATE_DARK),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 2.8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.8),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, SLATE_LIGHT]),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
    ]))
    story.append(risk_table)
    story.append(Spacer(1, 6))

    # Case Study Sub-section C
    story.append(Paragraph("C. Change Impact Blast Radius Execution", styles["SectionH2"]))
    impact_code = [
        "$ python analyzer-cli/analyze.py ./sample-projects/payment-service impact PaymentService.processPayment",
        "",
        "Impact Analysis for: processPayment (method)",
        "  Directly Affected: create (PaymentController.java), processPaymentPersistsRow (PaymentServiceTest.java)",
        "  Affected Database Objects: payments (table), PaymentEntity (class)",
        "  Affected Tests: processPaymentPersistsRow (PaymentServiceTest.java)",
        "  Note: Static impact analysis identifies potentially affected entities based on compile-time call graphs.",
    ]
    story.append(code_box(impact_code, styles))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 5: DASHBOARD TOUR, BENCHMARKS & QUICK START
    # =========================================================================
    story.append(Paragraph("5. Interactive Web Dashboard (10 Dedicated Views)", styles["SectionH1"]))
    story.append(Paragraph(
        "The React 18 + Vite + TypeScript frontend provides 10 dedicated navigation views for engineering teams:",
        styles["CustomBody"]
    ))

    fe_table_data = [
        [
            Paragraph("<b>View</b>", styles["TableHead"]),
            Paragraph("<b>Interface Functionality & Capabilities</b>", styles["TableHead"]),
        ],
        [
            Paragraph("<b>Projects & Upload</b>", styles["TableCellBold"]),
            Paragraph("Manage active projects, upload fresh repositories or ZIP archives, and trigger background analyses.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Overview Dashboard</b>", styles["TableCellBold"]),
            Paragraph("Executive summary with key metric cards: Total Files, Java Classes, Methods, Dependencies, Endpoints, and Tables.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Architecture Explorer</b>", styles["TableCellBold"]),
            Paragraph("Interactive multi-tier chain visualizer displaying verified Controller -> Service -> Repository -> Table flows.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Codebase Browser</b>", styles["TableCellBold"]),
            Paragraph("File tree and symbol catalog with instant filtering across classes, methods, annotations, and source lines.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Dependency Matrix</b>", styles["TableCellBold"]),
            Paragraph("Graph topological statistics, relationship breakdown by type (CALLS, IMPORTS), and upstream/downstream callers.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Ask Codebase</b>", styles["TableCellBold"]),
            Paragraph("Evidence-grounded conversational terminal. Returns verified text answers, step flows, and exact file:line cards.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Impact Analyzer</b>", styles["TableCellBold"]),
            Paragraph("Blast-radius simulator: select any class/method to inspect directly/indirectly impacted callers, APIs, and tests.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Risk Assessment</b>", styles["TableCellBold"]),
            Paragraph("Structural audit categorizing findings by severity (HIGH/MEDIUM) with exact metrics (fan-in/out, circularity).", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Modernization Planner</b>", styles["TableCellBold"]),
            Paragraph("Refactoring matrix identifying monolith decomposition candidates, high coupling bottlenecks, and framework upgrades.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Exportable Reports</b>", styles["TableCellBold"]),
            Paragraph("One-click generation and download of complete executive intelligence reports in Markdown or JSON.", styles["TableCell"]),
        ],
    ]
    fe_table = Table(fe_table_data, colWidths=[120, 412])
    fe_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), SLATE_DARK),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 2.2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.2),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, SLATE_LIGHT]),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
    ]))
    story.append(fe_table)
    story.append(Spacer(1, 6))

    # Benchmark & Quality Assurance
    story.append(Paragraph("6. Quality Assurance, Benchmark & Quick Start", styles["SectionH1"]))

    bench_summary_text = (
        "<b>Evaluation Benchmark Suite Results (P21):</b><br/>"
        "- <b>Scope:</b> 35 Grounded Evaluation Items across 10 categories (Architecture, Request Flow, Dependencies, Classes, Methods, APIs, Database, Impact, Risk, Modernization).<br/>"
        "- <b>Hallucination Rate:</b> <b>0.0%</b> (100% of entities, calls, and relationships verified against AST ground truth).<br/>"
        "- <b>Automated Test Suite:</b> 309 backend pytest tests (11.36s execution) + 6 frontend vitest tests passing (100% pass rate)."
    )
    story.append(callout_box(bench_summary_text, "BENCHMARK METRICS & TEST VERIFICATION", border_color=GREEN_ACCENT, bg_color=GREEN_BG, styles=styles))
    story.append(Spacer(1, 6))

    # Quick Start Commands Box
    deploy_code = [
        "# 1. Analyze sample project via CLI (Zero external configuration required)",
        "python analyzer-cli/analyze.py ./sample-projects/payment-service",
        "",
        "# 2. Trace request flows and change impact",
        "python analyzer-cli/analyze.py ./sample-projects/payment-service trace-request /api/payment",
        "python analyzer-cli/analyze.py ./sample-projects/payment-service impact PaymentService.processPayment",
        "",
        "# 3. Launch full stack with Docker Compose (PostgreSQL 16 + FastAPI Backend + React Dashboard)",
        "docker compose up -d --build",
        "# Dashboard: http://localhost:3000 | FastAPI Swagger API: http://localhost:8000/docs",
    ]
    story.append(code_box(deploy_code, styles))
    story.append(Spacer(1, 6))

    # Conclusion Sign-off Box
    concl_text = (
        "Enterprise AI delivers a rigorous, self-contained, enterprise-grade software intelligence solution. "
        "By enforcing strict AST determinism, relational persistence, and zero paid API dependencies, organizations "
        "can analyze, govern, and modernize legacy Java systems with complete architectural fidelity."
    )
    story.append(callout_box(concl_text, "VERIFICATION STATUS: ALL 23 PHASES VALIDATED & APPROVED", border_color=TEAL_ACCENT, bg_color=TEAL_BG, styles=styles))

    # Build Document
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated walkthrough PDF at: {output_path}")


if __name__ == "__main__":
    out_dir = Path(__file__).resolve().parent
    target_file = out_dir / "Enterprise_AI_Walkthrough.pdf"
    build_walkthrough_pdf(str(target_file))
