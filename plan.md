# Enterprise AI — Phase 1 Implementation Plan

## Product

Build an AI-powered Legacy Software Intelligence & Modernization platform.

Initial ecosystem:

- Java
- Spring
- Spring Boot
- SQL/database references

The long-term vision is an Enterprise AI platform, but Phase 1 must remain
focused on legacy Java software intelligence.

## Main Problem

A developer receives an unfamiliar Java/Spring codebase.

The system should help them:

- understand the repository
- discover architecture
- find classes and methods
- understand dependencies
- trace API/request flows
- ask questions about the codebase
- perform change-impact analysis
- identify measurable technical risks
- identify modernization candidates
- generate evidence-backed reports

## Core Architecture

Repository
→ Ingestion
→ Java Parser / AST
→ Symbols + Metadata
→ Dependency Graph
→ Structured Retrieval
→ Optional Semantic Retrieval
→ Evidence
→ Optional Local LLM
→ Q&A / Flow / Impact / Risk / Modernization
→ API
→ Dashboard

The repository and deterministic analysis are the source of truth.

The LLM explains evidence.

Never allow the LLM to invent repository facts.

---

# COST REQUIREMENT

The complete Phase 1 prototype must work without paid APIs.

Do NOT make any of these mandatory:

- OpenAI
- Anthropic
- Gemini
- Groq
- OpenRouter
- Pinecone
- AWS
- Azure
- GCP
- paid hosting
- paid vector databases
- paid embeddings

External APIs may be optional adapters later.

Default mode must be local/free.

---

# Technology Stack

## Backend

- Python 3.11+
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic

## Database

- PostgreSQL locally

## Java analysis

Use open-source/local Java parser or AST tooling.

Create a parser abstraction so the parser can be replaced later.

## Retrieval

Primary:

- PostgreSQL
- structured retrieval
- graph traversal

Optional:

- local embeddings
- local vector search

## AI

Use an abstraction:

LLMProvider
├── LocalLLMProvider
└── OptionalAPIProvider

The application must work when no LLM is configured.

## Frontend

- React / Next.js
- TypeScript

## Visualization

Use an open-source graph visualization library.

## Infrastructure

- Docker
- docker-compose

## Source control

- Git
- GitHub

---

# Product Rules

1. Do not build a generic chatbot.
2. Do not support every programming language.
3. Do not build cybersecurity in Phase 1.
4. Do not build cloud migration in Phase 1.
5. Do not build customer support.
6. Do not build a mobile application.
7. Do not train a foundation model.
8. Do not create dozens of autonomous agents.
9. Do not automatically modify production code.
10. Do not require paid APIs.
11. Do not send an entire repository to an LLM.
12. Parse and structure code before AI reasoning.
13. Use deterministic evidence wherever possible.
14. If evidence is insufficient, say so.
15. Never invent classes, methods, APIs, dependencies, tables or relationships.
16. Keep the architecture modular.
17. Do not introduce microservices.
18. Do not introduce Neo4j unless PostgreSQL becomes insufficient.
19. Build CLI functionality before the polished dashboard.
20. Test every stage before moving forward.

---

# Repository Structure

Create:

enterprise-ai/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── api/
│   │   ├── ingestion/
│   │   ├── parser/
│   │   ├── graph/
│   │   ├── retrieval/
│   │   ├── llm/
│   │   ├── analysis/
│   │   ├── reports/
│   │   ├── models/
│   │   └── security/
│   └── tests/
│
├── frontend/
│   └── src/
│
├── analyzer-cli/
│   └── analyze.py
│
├── evaluation/
├── sample-projects/
├── docs/
│
├── docker-compose.yml
├── .env.example
├── .gitignore
├── README.md
└── PLAN.md

---

# Implementation Phases

## P0 — Project Setup

Create:

- repository structure
- Python environment
- backend
- frontend
- configuration
- tests
- README
- .env.example
- .gitignore

Create a working health endpoint:

GET /health

---

# P1 — Repository Scanner

CLI:

python analyze.py ./repository

Also support:

python analyze.py ./repository.zip

Identify:

- Java files
- configuration
- SQL
- documentation
- pom.xml
- Gradle files

Ignore:

- .git
- node_modules
- target
- build
- dist
- binaries
- generated files where identifiable

ZIP extraction must prevent path traversal.

Output:

✓ Repository scanned
✓ Files discovered
✓ Java files discovered
✓ Configuration discovered
✓ Documentation discovered

---

# P2 — Java Parser

Create parser abstraction.

Extract where reliably possible:

- packages
- classes
- interfaces
- enums
- methods
- constructors
- fields
- imports
- annotations
- inheritance
- implemented interfaces
- method signatures
- method calls
- REST endpoints
- Spring annotations
- database references

Recognize common Spring annotations:

@Controller
@RestController
@Service
@Repository
@Component
@Autowired
@GetMapping
@PostMapping
@PutMapping
@DeleteMapping
@RequestMapping
@Entity
@Table
@Column

Every extracted entity should retain source-file information.

---

# P3 — Dependency Extraction

Create relationships:

- CONTAINS
- IMPORTS
- EXTENDS
- IMPLEMENTS
- CALLS
- USES
- EXPOSES
- QUERIES
- DEPENDS_ON
- REFERENCES
- TESTS

Example:

PaymentController
→ PaymentService
→ PaymentRepository
→ payments

Do not create relationships that cannot be resolved.

Unresolved relationships must be marked as unresolved.

---

# P4 — PostgreSQL Persistence

Create models for:

- projects
- repositories
- files
- packages
- classes
- interfaces
- methods
- fields
- imports
- dependencies
- graph_nodes
- graph_edges
- api_endpoints
- database_references
- analysis_runs
- documents
- code_chunks
- questions
- answers
- evidence
- impact_analyses
- risk_findings
- modernization_findings
- users
- audit_logs

Use migrations.

Add indexes for common lookups.

---

# P5 — Knowledge Graph

Represent software entities as graph nodes.

Represent relationships as graph edges.

Support:

- direct neighbors
- upstream dependencies
- downstream dependencies
- bounded traversal
- shortest relevant paths
- request-flow tracing
- impact traversal

Keep graph storage in PostgreSQL initially.

---

# P6 — CLI

Commands:

analyze
inspect
list-classes
list-methods
show-class
show-dependencies
show-graph
trace-request
impact
risks
ask
report

First major milestone:

python analyze.py ./sample-projects/payment-service

Expected:

✓ Repository scanned
✓ Java files parsed
✓ Packages discovered
✓ Classes discovered
✓ Methods discovered
✓ Imports extracted
✓ Dependencies extracted
✓ Architecture generated
✓ Risk analysis complete

---

# P7 — Structured Retrieval

Implement retrieval using:

- PostgreSQL
- symbols
- dependencies
- graph traversal
- source locations

Question:

"How does /api/payment reach the database?"

Retrieve:

- endpoint
- controller
- service
- method
- repository
- database
- dependency path
- source evidence

Do not require embeddings.

---

# P8 — Local Semantic Retrieval

Add optional local embeddings.

Index:

- classes
- methods
- documentation
- configuration
- SQL
- README

Store metadata:

- project_id
- repository_id
- file_id
- class_id
- method_id
- symbol_type

If embeddings are unavailable:

fall back to structured + keyword + graph retrieval.

---

# P9 — Local LLM

Create:

LLMProvider

Implement:

LocalLLMProvider

Optional:

APIProvider

The system must work without an LLM.

If no LLM exists:

"LLM unavailable — deterministic analysis mode enabled."

The LLM receives only relevant evidence.

---

# P10 — Evidence-Based Q&A

Question:

"How does /api/payment reach the database?"

Pipeline:

Question
→ Structured retrieval
→ Graph retrieval
→ Optional semantic retrieval
→ Evidence
→ Optional LLM
→ Answer

Return:

- answer
- evidence
- flow
- limitations

Evidence must reference actual files/classes/methods.

If evidence is insufficient:

"Insufficient evidence in the analyzed repository."

---

# P11 — Request Flow

Implement:

trace-request "/api/payment"

Expected:

/api/payment
→ PaymentController
→ PaymentService
→ PaymentRepository
→ payments

Each step must have source evidence.

Unresolved steps must be reported.

---

# P12 — Change Impact

Implement:

impact "PaymentService.processPayment"

Trace:

- direct callers
- indirect callers
- services
- controllers
- repositories
- APIs
- database references
- tests

Use bounded graph traversal.

Use:

"Potentially affected"

instead of claiming guaranteed breakage.

---

# P13 — Risk Analysis

Use measurable indicators:

- dependency count
- fan-in
- fan-out
- class size
- method count
- complexity where available
- circular dependencies
- inheritance depth
- API exposure
- database coupling
- test presence

Do not create arbitrary AI scores.

Example:

HIGH DEPENDENCY COMPONENT

PaymentService

Evidence:

17 incoming dependencies
11 outgoing dependencies

Explain the metrics.

---

# P14 — Architecture Visualization

Expose:

- packages
- modules
- controllers
- services
- repositories
- databases
- APIs
- integrations
- tests

Provide graph data for frontend.

---

# P15 — Modernization Analysis

After structural analysis, identify evidence-backed candidates:

- high coupling
- circular dependencies
- large classes
- high dependency components
- architectural bottlenecks
- testing gaps
- possible decomposition candidates
- detectable framework modernization opportunities

Return:

- finding
- evidence
- reason
- possible direction
- dependencies
- risk
- investigation order

Do not automatically modify code.

---

# P16 — Reports

Generate:

- Markdown
- JSON

Report sections:

1. Executive summary
2. Repository inventory
3. Architecture
4. Dependencies
5. Request flows
6. Risks
7. Impact analysis
8. Modernization
9. Test observations
10. Evidence
11. Limitations

---

# P17 — FastAPI

Implement:

GET /health

POST /projects
GET /projects
GET /projects/{id}

POST /projects/{id}/repositories
POST /projects/{id}/analyze

GET /projects/{id}/files
GET /projects/{id}/classes
GET /projects/{id}/methods

GET /projects/{id}/architecture
GET /projects/{id}/graph

POST /projects/{id}/questions
POST /projects/{id}/impact

GET /projects/{id}/risks
GET /projects/{id}/modernization

POST /projects/{id}/reports

GET /projects/{id}/analysis-runs

Validate project access.

---

# P18 — Frontend

Create:

Dashboard
Projects
Architecture
Codebase
Dependencies
Ask Codebase
Impact
Risks
Modernization
Reports

Project dashboard:

Files
Classes
Methods
Dependencies
APIs
Database references

Ask Codebase:

question input
answer
evidence
flow

Impact:

class/method selection
affected components
evidence

Risks:

deterministic metrics

Modernization:

evidence-backed findings

Keep UI simple.

---

# P19 — Security

Implement:

- authentication abstraction
- authorization
- project isolation
- safe ZIP extraction
- upload limits
- secret management
- audit logs
- temporary file cleanup

Never commit secrets.

Never log API keys/passwords/tokens.

---

# P20 — Docker

Create docker-compose.yml.

Services:

- PostgreSQL
- backend
- frontend

Everything must work locally.

Do not require cloud infrastructure.

---

# P21 — Evaluation

Create 30–50 evaluation questions covering:

- architecture
- request flow
- dependencies
- classes
- methods
- APIs
- database interaction
- impact
- risks
- modernization

Track:

- retrieval correctness
- evidence correctness
- entity correctness
- relationship correctness
- answer grounding
- hallucination
- impact correctness

---

# P22 — Testing

Every phase must include tests.

Run:

- unit tests
- parser tests
- graph tests
- database tests
- retrieval tests
- API tests
- security tests
- integration tests
- evaluation tests
- end-to-end tests

Do not proceed to the next phase if the current phase is broken.

---

# Sample Project

Create:

sample-projects/payment-service/

Containing:

PaymentController
PaymentService
PaymentRepository
PaymentEntity
payments table
PaymentServiceTest

Include:

- REST endpoint
- Controller → Service → Repository
- database reference
- multiple callers
- tests
- circular dependency example
- high fan-out example

This becomes the primary test fixture.

---

# First Goal

DO NOT start with the dashboard.

Make this work first:

python analyze.py ./sample-projects/payment-service

Then:

python analyze.py ./sample-projects/payment-service ask \
"How does /api/payment reach the database?"

Then:

python analyze.py ./sample-projects/payment-service impact \
"PaymentService.processPayment"

The system must work without any paid API.

---

# Definition of Done

[ ] Repository ingestion
[ ] ZIP ingestion
[ ] Java parsing
[ ] Classes
[ ] Methods
[ ] Interfaces
[ ] Imports
[ ] Inheritance
[ ] Calls
[ ] Spring endpoints
[ ] Database references
[ ] Dependency graph
[ ] PostgreSQL
[ ] CLI
[ ] Architecture
[ ] Request tracing
[ ] Structured retrieval
[ ] Optional semantic retrieval
[ ] Local LLM support
[ ] Evidence-backed Q&A
[ ] Impact analysis
[ ] Risk analysis
[ ] Modernization analysis
[ ] Reports
[ ] FastAPI
[ ] Dashboard
[ ] Security
[ ] Docker
[ ] Evaluation
[ ] Tests

---

# Development Rule

Do NOT implement all phases at once.

Implement one phase at a time.

After each phase:

1. Run tests.
2. Run the sample project.
3. Inspect actual output.
4. Fix failures.
5. Update documentation.
6. Only then move to the next phase.

The first implementation task is P0 + P1 only.