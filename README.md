# Enterprise AI — Legacy Software Intelligence & Modernization Platform

An AI-powered software intelligence platform designed for legacy **Java**, **Spring**, **Spring Boot**, and SQL/database systems.

**Zero paid APIs required.** Scanning, AST parsing, knowledge graph construction, dependency traversal, impact analysis, risk assessment, request tracing, and evidence-backed Q&A all function completely locally and deterministically without OpenAI, Anthropic, cloud vector databases, or paid embeddings.

---

## Current Status: Phase 1 Complete (P0–P22)

All 23 implementation milestones defined in [`plan.md`](file:///c:/Users/amogh/Downloads/FOLDERS/NS-4/plan.md) are fully implemented, verified, and passing:

| Phase | Milestone | Scope / Capabilities | Status |
|-------|-----------|----------------------|--------|
| **P0** | **Project Setup** | Modular structure, FastAPI entrypoint, health endpoints, environment configuration | Complete |
| **P1** | **Repository Scanner** | Directory + safe ZIP extraction (anti-path-traversal), file inventory classification | Complete |
| **P2** | **Java AST Parser** | Pluggable AST abstraction (`javalang`), classes, methods, fields, annotations, Spring & SQL refs | Complete |
| **P3** | **Dependency Extraction** | In-memory relational graph (`CONTAINS`, `CALLS`, `EXTENDS`, `EXPOSES`, `QUERIES`, `TESTS`) | Complete |
| **P4** | **PostgreSQL Persistence** | Relational persistence models, Alembic migrations, snapshot versioning | Complete |
| **P5** | **Knowledge Graph** | Bounded multi-hop traversal, cycle detection, shortest paths, upstream/downstream callers | Complete |
| **P6** | **Unified CLI** | 13 subcommands (`analyze`, `ask`, `impact`, `trace-request`, `risks`, `report`, etc.) | Complete |
| **P7** | **Structured Retrieval** | Deterministic symbol and call-chain retrieval from PostgreSQL & graph indices | Complete |
| **P8** | **Semantic Retrieval** | Local TF-IDF & vector embedding fallback for symbols, docstrings, and SQL schemas | Complete |
| **P9** | **Local / Free LLM Layer** | Provider abstraction (`LocalLLMProvider`, `OptionalAPIProvider`), deterministic zero-cost fallback | Complete |
| **P10** | **Evidence-Based Q&A** | Grounded question answering pipeline with file/line evidence citation & flow steps | Complete |
| **P11** | **Request Flow Tracing** | Deterministic end-to-end tracing: REST Endpoint → Controller → Service → Repository → DB Table | Complete |
| **P12** | **Change Impact Analysis** | Bounded transitive blast-radius analysis across callers, APIs, database entities, and tests | Complete |
| **P13** | **Technical Risk Analysis** | Deterministic metrics: circular dependencies, fan-in/fan-out orchestration, test coverage gaps | Complete |
| **P14** | **Architecture Visualization**| Multi-tier architectural layer grouping (controllers, services, repositories, DB, tests) | Complete |
| **P15** | **Modernization Advisor** | Evidence-backed decoupling recommendations, cyclic break suggestions, decomposition steps | Complete |
| **P16** | **Report Generator** | Production-ready Markdown & JSON executive and technical report generation | Complete |
| **P17** | **Production FastAPI API** | REST API covering projects, graph, flow, impact, risks, modernization, and reports | Complete |
| **P18** | **Interactive Web Dashboard**| 10-page React + TypeScript frontend with interactive SVG dependency graph | Complete |
| **P19** | **Security & Isolation** | Project boundary isolation, upload sanitization, ZIP-slip prevention, audit logging | Complete |
| **P20** | **Docker Orchestration** | Multi-container `docker-compose.yml` for PostgreSQL, FastAPI backend, and Nginx frontend | Complete |
| **P21** | **Evaluation Benchmark** | 30+ standardized evaluation test cases covering retrieval accuracy and hallucination defense | Complete |
| **P22** | **Full Automated Test Suite** | 309 backend pytest tests (100% pass) + 6 frontend vitest tests (100% pass) | Complete |

---

## Core Architecture

```
Repository / ZIP Archive
   │
   ▼
Ingestion & Safe Scanner (P1)
   │
   ▼
Java Parser & AST Extraction (P2)
   │
   ▼
Dependency Graph Builder (P3, P5) ───► PostgreSQL Storage & Snapshots (P4)
   │                                           │
   ▼                                           ▼
Structured & Graph Retrieval (P7) ◄──── Semantic Retrieval Fallback (P8)
   │
   ▼
Deterministic Evidence Collector
   │
   ▼
Optional Local LLM Provider (P9) (Strictly grounds explanations on evidence)
   │
   ├─► Q&A Engine (P10)
   ├─► Request Flow Tracing (P11)
   ├─► Change Impact Analysis (P12)
   ├─► Technical Risk Assessment (P13)
   ├─► Architecture Modeling (P14)
   ├─► Modernization Findings (P15)
   └─► Markdown / JSON Reports (P16)
   │
   ▼
FastAPI REST Service (P17) ───► React + TypeScript Dashboard (P18)
```

> **Design Principle:** Deterministic code analysis is the sole source of truth. The LLM only explains verified evidence and is never permitted to invent classes, methods, endpoints, or dependencies. If evidence is insufficient, the system explicitly reports it.

---

## Repository Layout

```
├── backend/
│   ├── app/
│   │   ├── analysis/       # Architecture, impact, modernization, Q&A, risks
│   │   ├── api/            # FastAPI route controllers
│   │   ├── evaluation/     # Benchmark dataset and evaluation runner
│   │   ├── graph/          # AST extraction, relational graph, traversal algorithms
│   │   ├── ingestion/      # Safe filesystem & ZIP repository scanner
│   │   ├── llm/            # Local & API LLM provider abstractions
│   │   ├── models/         # SQLAlchemy schema & Pydantic domain models
│   │   ├── parser/         # Java AST parser (javalang) & metadata extractor
│   │   ├── reports/        # Markdown & JSON report generators
│   │   ├── retrieval/      # Structured, semantic, and hybrid retrieval engines
│   │   ├── security/       # Sanitization, audit logging, project isolation
│   │   ├── config.py       # Pydantic environment configuration
│   │   ├── database.py     # SQLAlchemy session & engine management
│   │   ├── main.py         # FastAPI application entrypoint
│   │   └── persistence.py  # Repository snapshot persistence handlers
│   ├── migrations/         # Alembic database migration scripts
│   ├── tests/              # 309 unit, integration, and E2E test cases
│   └── Dockerfile          # Backend container image
├── frontend/
│   ├── src/
│   │   ├── api/            # Typed API client with offline demo fallbacks
│   │   ├── components/     # Interactive SVG graph & navigation sidebar
│   │   ├── pages/          # 10 specialized intelligence views
│   │   ├── App.tsx         # Main application shell
│   │   └── types.ts        # TypeScript domain models
│   ├── package.json        # Vite, React 18, Vitest configuration
│   ├── nginx.conf          # Frontend production reverse proxy config
│   └── Dockerfile          # Frontend container image
├── analyzer-cli/
│   └── analyze.py          # Unified CLI supporting 13 subcommands
├── sample-projects/
│   └── payment-service/    # Fixture Spring Boot app (controllers, services, SQL, cycles)
├── docs/                   # Platform documentation and walkthrough PDFs
├── docker-compose.yml      # Orchestration for PostgreSQL, Backend, and Frontend
└── plan.md                 # 23-phase implementation roadmap and requirements
```

---

## Quick Start

### Option A: Run Everything with Docker Compose (Recommended)

Start PostgreSQL, the FastAPI backend, and the React frontend with a single command:

```bash
docker compose up --build -d
```

- **Frontend Dashboard:** [http://localhost:3000](http://localhost:3000)
- **FastAPI Backend & Interactive Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Backend Health Check:** [http://localhost:8000/health](http://localhost:8000/health)

---

### Option B: Local Development Setup

#### 1. Backend Setup (Python 3.11+)

```bash
cd backend

# Create virtual environment
py -3.11 -m venv .venv

# Activate on Windows
.venv\Scripts\activate
# Activate on Linux/macOS
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

#### 2. Configure Environment & Database

Copy the example environment configuration:

```bash
cp .env.example .env
```

Start the local PostgreSQL container and run database migrations:

```bash
docker compose up -d postgres
cd backend
alembic upgrade head
cd ..
```

#### 3. Start the Backend API

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

#### 4. Start the Frontend Dashboard

In a new terminal:

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## CLI Usage (`analyzer-cli/analyze.py`)

The unified CLI works on both local directories and `.zip` archives.

### 1. Full Repository Scan & Parsing

```bash
python analyzer-cli/analyze.py ./sample-projects/payment-service
```

Optional flags:
- `--json`: Output results as structured JSON
- `--list-files`: List all discovered source files, configs, SQL, and docs
- `--list-types`: Display packages, classes, interfaces, and endpoints
- `--persist`: Persist the analysis run snapshot into PostgreSQL
- `--verify-arch`: Verify standard Controller → Service → Repository layering

### 2. Evidence-Backed Codebase Q&A (`ask`)

Ask questions about architecture and data flow without hallucinations:

```bash
python analyzer-cli/analyze.py ./sample-projects/payment-service ask "How does /api/payment reach the database?"
```

### 3. Change Impact Analysis (`impact`)

Trace the blast radius of modifying a specific class or method:

```bash
python analyzer-cli/analyze.py ./sample-projects/payment-service impact "PaymentService.processPayment"
```

Outputs:
- Target symbol details & source file location
- Direct and indirect callers
- Exposed API endpoints affected
- Database tables and JPA entities impacted
- Relevant unit tests that require execution

### 4. End-to-End Request Flow Tracing (`trace-request`)

Reconstruct the execution path from an HTTP route down to the database:

```bash
python analyzer-cli/analyze.py ./sample-projects/payment-service trace-request "/api/payment"
```

### 5. Measurable Technical Risk Analysis (`risks`)

Evaluate structural risks using objective codebase metrics:

```bash
python analyzer-cli/analyze.py ./sample-projects/payment-service risks
```

Detects:
- **Circular dependencies** (e.g. `PaymentService` ↔ `NotificationService`)
- **High fan-in/fan-out orchestration hubs** (e.g. `PaymentService`)
- **Untested high-risk classes**
- **Deep inheritance and high coupling**

### 6. Generate Comprehensive Reports (`report`)

Generate complete audit reports in Markdown or JSON format:

```bash
# Markdown report
python analyzer-cli/analyze.py ./sample-projects/payment-service report --output report.md

# Machine-readable JSON report
python analyzer-cli/analyze.py ./sample-projects/payment-service report --json --output report.json
```

---

## FastAPI REST API Endpoints

The backend provides a complete RESTful API:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Service health status and database connectivity |
| `POST` | `/projects` | Register a new software intelligence project |
| `GET` | `/projects` | List all registered projects |
| `GET` | `/projects/{id}` | Retrieve project details and latest snapshot |
| `POST` | `/projects/{id}/analyze` | Trigger repository ingestion and AST analysis |
| `GET` | `/projects/{id}/files` | File inventory by classification |
| `GET` | `/projects/{id}/classes` | Discovered classes, methods, and annotations |
| `GET` | `/projects/{id}/architecture` | Layered architecture summary |
| `GET` | `/projects/{id}/graph` | Knowledge graph nodes and edges for visualization |
| `POST` | `/projects/{id}/questions` | Evidence-grounded natural language Q&A |
| `POST` | `/projects/{id}/flow` | Request-flow call chain tracing |
| `POST` | `/projects/{id}/impact` | Bounded change-impact blast-radius analysis |
| `GET` | `/projects/{id}/risks` | Deterministic technical risk report |
| `GET` | `/projects/{id}/modernization`| Evidence-backed modernization recommendations |
| `POST` | `/projects/{id}/reports` | Generate Markdown or JSON analysis reports |
| `GET` | `/projects/{id}/analysis-runs` | History of persisted analysis runs |

Interactive Swagger documentation is available at `http://localhost:8000/docs`.

---

## Frontend Dashboard (P18)

The React dashboard provides a responsive, dark-mode workspace:

1. **Dashboard:** High-level project metrics (files, classes, methods, endpoints, database entities, risk scores).
2. **Projects:** Multi-project management, repository upload, and historical run inspection.
3. **Architecture:** Component breakdown across controllers, services, repositories, database models, and utilities.
4. **Codebase:** File explorer, AST symbols, class hierarchies, and source details.
5. **Dependencies & Graph:** Interactive SVG dependency graph with category toggles, zoom/pan, and node inspector.
6. **Ask Codebase:** Natural language Q&A interface with source code line citations and call path diagrams.
7. **Impact Analysis:** Interactive blast radius calculator showing affected APIs, callers, tables, and test cases.
8. **Technical Risks:** Severity-ranked findings with underlying metrics (cycle length, fan-in/fan-out counts).
9. **Modernization:** Guided roadmap for microservice extraction, breaking cycles, and legacy framework upgrades.
10. **Reports:** In-browser Markdown and JSON report generator and viewer.

---

## Testing & Quality Assurance

### Run Backend Tests (309 tests)

```bash
cd backend
pytest -v
```

Tests cover:
- Repository scanner & ZIP path-traversal safety (`test_scanner.py`, `test_zip_safety.py`)
- Java AST extraction & annotation parsing (`test_parser.py`, `test_detectors.py`)
- Dependency extraction & relation graphs (`test_dependency_extraction.py`, `test_knowledge_graph.py`)
- PostgreSQL persistence & Alembic migrations (`test_persistence.py`, `test_migrations.py`)
- Retrieval engines (`test_structured_retrieval.py`, `test_semantic_retrieval.py`)
- LLM provider abstraction & zero-cost mode (`test_llm_provider.py`)
- Flow tracing & impact analysis (`test_request_flow.py`, `test_impact_analysis.py`)
- Risk & modernization algorithms (`test_risk_analysis.py`, `test_modernization_analysis.py`)
- Security & project isolation (`test_security.py`)
- Evaluation benchmark harness (`test_evaluation_framework.py`)
- End-to-end integration flows (`test_end_to_end_validation.py`)

### Run Frontend Tests (6 tests)

```bash
cd frontend
npm test
```

Verifies routing across all 10 pages, navigation interactions, and API fallback resilience.

---

## Sample Fixture (`sample-projects/payment-service`)

A realistic legacy Spring Boot reference project included for testing:

- **End-to-End Request Chain:** `PaymentController` (`POST /api/payment`) → `PaymentService` (`processPayment`) → `PaymentRepository` (`save`) → `payments` SQL table.
- **Architectural Complexities:**
  - Bidirectional circular dependency between `PaymentService` and `NotificationService`.
  - High fan-out orchestrator (`MetricsFacade` / `PaymentService`).
  - Multi-caller routes (`PaymentController`, `RefundController`).
  - Unit test coverage verification via `PaymentServiceTest`.

---

## Cost & Privacy Guarantees

| Capability | Default Platform Mode | Paid Cloud Alternative |
|------------|-----------------------|------------------------|
| **Repository Scanning** | 100% Local Filesystem / In-Memory | None needed |
| **Parsing & AST** | 100% Local `javalang` AST | None needed |
| **Dependency Graph** | 100% Local In-Memory & PostgreSQL | No graph cloud DB needed |
| **Vector Search / Retrieval** | Local TF-IDF & local embeddings | Pinecone / Weaviate not required |
| **Reasoning Engine** | Deterministic Evidence Engine (`LLM_ENABLED=false`) | Optional OpenAI / Anthropic adapter |
| **Database** | Local PostgreSQL Container | Cloud RDS not required |

Your source code never leaves your local environment unless you explicitly configure an external LLM API key.
