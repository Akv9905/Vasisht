# Enterprise AI — Phase 1 (P0–P4)

Local/free legacy Java & Spring software intelligence platform.

**Paid APIs are never required.** Scanning and analysis work without OpenAI, Anthropic, cloud vector DBs, or paid embeddings.

## Current status

| Phase | Scope | Status |
|-------|--------|--------|
| **P0** | Project structure, FastAPI health, config, frontend placeholder, tests | Done |
| **P1** | Repository scanner (directory + safe ZIP), file inventory, detectors, sample project | Done |
| **P2** | Java parser abstraction, AST extraction, Spring/REST/DB refs | Done |
| **P3** | In-memory dependency graph extraction | Done |
| **P4** | PostgreSQL persistence models, migrations, analysis snapshots | In progress (code and SQLite migration verified; live PostgreSQL run pending) |
| P5+ | Graph traversal, retrieval, LLM, dashboard, … | Not started |

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

### 2. Scan and parse the sample project (P1 + P2)

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
python analyzer-cli/analyze.py ./sample-projects/payment-service --list-types
python analyzer-cli/analyze.py ./sample-projects/payment-service --json
python analyzer-cli/analyze.py ./sample-projects/payment-service --scan-only
```

ZIP archives are also supported (path traversal is blocked):

```bash
python analyzer-cli/analyze.py ./path/to/repo.zip
```

### 3. Persist analysis results (P4)

Start the local PostgreSQL service and apply the schema migration:

```bash
docker compose up -d --wait postgres
cd backend
alembic upgrade head
cd ..
```

Copy `.env.example` to `.env` if needed, then persist the sample analysis:

```bash
python analyzer-cli/analyze.py ./sample-projects/payment-service --persist
```

Each run is stored as a historical snapshot. To use another project label, add
`--project-name "My project"`. `DATABASE_URL` can point at another PostgreSQL
database; migrations must be applied before using `--persist`.

### 4. Health API (P0)

```bash
cd backend
uvicorn app.main:app --reload --app-dir .
```

Then open `http://127.0.0.1:8000/health`.

### 5. Tests

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
| Database | Local PostgreSQL for persistence; scanning remains available without it |
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

## Known limitations (P0–P4)

- Dependency graph extraction exists; traversal, Q&A, impact, and risk analysis remain later phases
- Frontend is a placeholder only
- PostgreSQL is configured but not required for scanning/parsing
- Parser uses `javalang` — some newer Java syntax may fail per-file (reported as parse errors)
- Method-call extraction is syntactic (qualifier + name), not fully resolved to declarations
