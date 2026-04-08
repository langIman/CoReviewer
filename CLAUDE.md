# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CoReviewer is a structured code review tool for AI-generated codebases. It combines AST-based static analysis, a multi-agent LLM system, and interactive ReactFlow visualization. Only Python files (`.py`) are supported for analysis.

## Commands

### Backend
```bash
pip install -r backend/requirements.txt
PYTHONPATH=. uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev      # Dev server (Vite 8)
npm run build    # tsc -b && vite build
npm run lint     # ESLint
```

### Makefile
```bash
make install     # Install all deps (pip + npm)
make dev         # Backend (background) + frontend
make backend     # Backend only
make frontend    # Frontend only
```

### Environment
Copy `.env.example` to `.env` and set `QWEN_API_KEY`, `QWEN_BASE_URL`, `QWEN_MODEL`.

### Testing
No test framework is configured. No test files exist in the codebase.

## Architecture

### Backend (FastAPI, Python)

MVC structure under `backend/`:

- **`main.py`** — Entry point; registers 4 routers (`file`, `review`, `graph`, `summary`), sets up CORS, initializes SQLite via `init_db()`
- **`controllers/`** — HTTP layer: `file_controller`, `review_controller`, `graph_controller`, `summary_controller`
- **`services/`** — Business logic:
  - `review_service.py` — Orchestrates LLM streaming review
  - `overview_service.py` / `detail_service.py` — Flowchart generation, delegates to agents
  - `summary_service.py` — Hierarchical summary generation (file → folder → project)
  - `agents/lead.py` + `agents/worker.py` — Multi-agent system (see below)
  - `llm/llm_service.py` — Qwen API wrapper (OpenAI-compatible); `call_qwen()` (120s timeout) and `stream_qwen()` (60s timeout, SSE)
  - `llm/prompts/` — Prompt templates including `summary_prompts.py` (Chinese-language prompts for file/folder/project summaries)
- **`utils/analysis/`** — AST pipeline: `call_graph.py` → `import_analysis.py` → `entry_detector.py`
- **`dao/`** — Storage:
  - In-memory: `file_store.py`, `knowledge_base.py` (per-request, stores `FunctionSummary`), `graph_cache.py`
  - Persistent: `database.py` + `summary_store.py` → SQLite at `backend/data/summaries.db`
- **`models/`** — Pydantic schemas: `schemas.py`, `graph_models.py`, `agent_models.py`

### Frontend (React 19 + TypeScript, Vite 8)

- **`App.tsx`** — Root layout with drag-drop `.py` file collection (uses `webkitGetAsEntry()` for directory recursion)
- **`store/useReviewStore.ts`** — Zustand store: file, project, selection, responses, highlight state
- **`services/api.ts`** — All backend API calls
- **`components/Diagrams/FlowChart.tsx`** — ReactFlow (`@xyflow/react`) DAG with drill-down navigation
- **`components/CodeView/`** — Syntax-highlighted code with line selection
- **`components/AIPanel/`** — Streaming AI review responses, anchored to line ranges
- **`i18n/`** — `locales.ts` (zh/en, 80+ keys), `LanguageContext.tsx`, `ThemeContext.tsx` — separate React contexts (not in Zustand)

### Key Data Flows

**Single-file review:** Upload `.py` → user selects lines → `POST /api/review` streams SSE → displayed in AIPanel anchored to selected lines.

**Project flowchart generation:**
1. `POST /api/file/upload-project` → builds `ProjectAST` (definitions, call edges, entry points, imports)
2. `POST /api/graph/overview` → Lead Agent scores functions by "business density" (`DENSITY_THRESHOLD = 5.0`), spawns concurrent Workers to summarize callees via LLM, then LLM generates `FlowData {nodes, edges}`
3. `POST /api/graph/detail` → expands a single node to show its internal logic

**Hierarchical summary generation:**
1. `POST /api/summary/generate` → extracts AST skeletons per file (function/class signatures, truncated to `SUMMARY_TRUNCATION_PERCENT = 0.3`)
2. LLM summarizes each file → aggregates into folder summaries → produces project summary
3. If LLM responds "信息不足无法推测", retries with full file content
4. All summaries persisted to SQLite (`summaries` table: path, type, summary, project_name)

**Multi-agent system (`services/agents/`):**
- Lead agent selects key function, collects 2-level deep callees, spawns Worker pool (`MAX_WORKER_CONCURRENCY = 5` in `agents/config.py`)
- Workers concurrently call LLM to summarize functions → write `FunctionSummary` to `KnowledgeBase`
- Lead waits for all workers via `mailbox.py`, then generates the final flowchart prompt

### AST Pipeline (`utils/analysis/`)

`call_graph.py` parses all `.py` files → extracts `SymbolDef` (functions/classes) and `CallEdge` (call sites) → `import_analysis.py` resolves cross-file imports → `entry_detector.py` identifies routes, CLI commands, `__main__` guards → produces `ProjectAST` (cached in `graph_cache.py` by file hash).

### API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/file/upload` | Single `.py` file |
| POST | `/api/file/upload-project` | Multiple files as project |
| POST | `/api/file/project/summary` | LLM project overview |
| POST | `/api/review` | Streaming SSE code review |
| POST | `/api/graph/overview` | Generate overview flowchart |
| POST | `/api/graph/detail` | Expand node to detail flowchart |
| POST | `/api/summary/generate` | Hierarchical summary (file→folder→project) |
| GET | `/api/health` | Health check |

### Configuration (`backend/config.py` + `agents/config.py`)

- `MAX_FILE_SIZE = 1MB`, `MAX_PROJECT_SIZE = 10MB`, `MAX_PROJECT_FILES = 200`
- `ALLOWED_EXTENSIONS = {".py"}`
- `SUMMARY_FUNC_LINES = 5`, `SUMMARY_TRUNCATION_PERCENT = 0.3`
- `MAX_WORKER_CONCURRENCY = 5`, `DENSITY_THRESHOLD = 5.0`
