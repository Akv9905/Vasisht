# Enterprise AI — Phase 1 (P0 + P1)

Local/free legacy Java & Spring software intelligence platform.

**Paid APIs are never required.** Scanning and analysis work without OpenAI, Anthropic, cloud vector DBs, or paid embeddings.

## Current status

| Phase | Scope | Status |
|-------|--------|--------|
| **P0** | Project structure, FastAPI health, config, frontend placeholder, tests | Done |
| **P1** | Repository scanner (directory + safe ZIP), file inventory, detectors, sample project | Done |
| P2+ | Java parser, graph, retrieval, LLM, dashboard, … | Not started |

## Repository layout

```
backend/           FastAPI app + ingestion scanner
analyzer-cli/      CLI entrypoint
frontend/          Placeholder UI (dashboard comes later)
sample-projects/   Fixture Java/Spring apps
docs/              Documentation
evaluation/        Evaluation harness (later)
```

## Quick start

### 1. Python environment

Requires **Python 3.11+**. On Windows, prefer the `py` launcher if `python` points at MSYS:

```bash
cd backend
py -3.11 -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Optional: copy `.env.example` to `.env` at the repo root.

### 2. Scan the sample project (P1)

From the repository root:

```bash
python analyzer-cli/analyze.py ./sample-projects/payment-service
```

On Windows, if checkmarks fail to print, set `PYTHONIOENCODING=utf-8` or use:

```bash
py -3.11 analyzer-cli/analyze.py ./sample-projects/payment-service
```

Useful flags:

```bash
python analyzer-cli/analyze.py ./sample-projects/payment-service --list-files
python analyzer-cli/analyze.py ./sample-projects/payment-service --json
```

ZIP archives are also supported (path traversal is blocked):

```bash
python analyzer-cli/analyze.py ./path/to/repo.zip
```

### 3. Health API (P0)

```bash
cd backend
uvicorn app.main:app --reload --app-dir .
```

Then open `http://127.0.0.1:8000/health`.

### 4. Tests

```bash
cd backend
pytest -q
```

## Architecture (target)

```
Repository → Parser → Structured Metadata → Graph → Retrieval → Evidence → Optional LLM → Result
```

The LLM is **not** the source of truth. Deterministic scanning and (later) parsing come first.

## Cost / providers

| Capability | Default |
|------------|---------|
| Repository scan | Local filesystem / ZIP |
| Database | Optional PostgreSQL (unused in P0/P1 scan path) |
| LLM | Disabled (`LLM_ENABLED=false`) |
| Embeddings | Not required |

## Sample fixture

`sample-projects/payment-service/` includes:

- `PaymentController` → `PaymentService` → `PaymentRepository` → `payments`
- SQL schema, Spring config, README
- Circular dependency (`PaymentService` ↔ `NotificationService`)
- High fan-out helper (`MetricsFacade`)
- Multiple callers (`PaymentController`, `RefundController`)
- `PaymentServiceTest`

## Known limitations (P0/P1)

- No Java AST parsing yet (P2)
- No dependency graph, Q&A, impact, or risk analysis
- Frontend is a placeholder only
- PostgreSQL is configured but not required for scanning
