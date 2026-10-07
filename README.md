# DevForge — AI-Assisted Software Engineering Platform Using Multi-Agent Collaboration

A production-grade prototype where **six specialized AI agents** collaborate, under an
explicit **human-in-the-loop state machine**, to take a software project from a one-line
prompt all the way to an approved, tested, security-scanned, documented and git-committed
codebase.

```
                        ┌────────────────────────────────────────────────────────────┐
  user prompt ─────────►│  1. Requirement Agent ──G1──► 2. Architecture Agent ──G2──► │
                        │        ▲  reject                ▲ reject                    │
                        │        └── feedback ──┘         └── feedback ─┘              │
                        │  3. Coding Agent ──G3──► 4. Testing Agent                    │
                        │        ▲  reject              │ D4: pytest fails             │
                        │        └── feedback ──┘        └──► coding (self-heal, no gate)
                        │  5. Security Agent ◄───────────┘                             │
                        │        │ D5: HIGH finding ──► coding (fix, no gate) ─► re-scan
                        │  6. Documentation Agent ──G6──► 7. Delivery & GitSync ──► ✅  │
                        └────────────────────────────────────────────────────────────┘
```

**G1–G6** are human approval gates (Approve / Reject / Request Changes with comments — the
comment is injected into the agent's next prompt). **D4/D5** are automated decision loops
with bounded self-healing (no human gate), which is exactly the workflow specified for the
project.

---

## Repository layout

```
devforge/
├── backend/
│   ├── app/
│   │   ├── agents/               # RA, AA, CA, TA, SA, DocA (Pydantic schema-bound)
│   │   ├── orchestrator/         # state.py (state schema) + workflow_engine.py (state machine)
│   │   ├── execution/            # runner.py (subprocess pytest + bandit/AST scanner), git_service.py
│   │   ├── db/                   # SQLAlchemy models + session (SQLite)
│   │   ├── routers/              # projects.py, approvals.py, execution.py
│   │   ├── llm/                  # provider abstraction (OpenAI/Groq/Anthropic/mock) + templates
│   │   ├── streaming/            # SSE event bus
│   │   ├── core/                 # settings (.env), errors
│   │   ├── utils/                # safe workspace file I/O, markdown renderers
│   │   └── main.py               # FastAPI app
│   ├── requirements.txt
│   └── .env.example
├── frontend/                     # React + Vite + TypeScript + Tailwind + Lucide
│   ├── src/
│   │   ├── components/           # PipelineVisualizer, ApprovalModal, CodeViewer, LogsConsole
│   │   ├── pages/Dashboard.tsx   # multi-role workspace (Developer/Architect/Tester/PM)
│   │   └── lib/                  # api client (fetch + SSE), types, markdown renderer
│   ├── package.json
│   └── tailwind.config.js
├── scripts/
│   ├── e2e_smoke.py              # full-pipeline smoke test (auto-approves gates)
│   └── test_loops.py             # verifies reject / D4 self-heal / D5 fix loops
└── workspaces/{project_id}/      # generated project files (src, tests, docs, .git, CI)
```

---

## Quickstart (local)

Prereqs: **Python 3.11+**, **Node 18+**, **git**.

### 1. Backend (FastAPI, port 8000)

```bash
cd devforge/backend
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # optional — defaults work out of the box
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive API docs: http://localhost:8000/docs

> No `.env` needed to try it: with `LLM_PROVIDER=auto` and no API keys, DevForge
> falls back to its built-in **deterministic mock LLM**, which generates a complete,
> runnable, security-clean codebase so the whole pipeline works offline.

### 2. Frontend (Vite, port 5173)

```bash
cd devforge/frontend
npm install
npm run dev
```

Open **http://localhost:5173** — the dev server proxies `/api/*` to the backend.

### 3. Run a project

1. Click **New Project**, name it (e.g. `URL Shortener`), and describe the task.
2. Click **Start Multi-Agent Workflow**.
3. Watch the pipeline visualizer move through the stages; at each **approval gate** an
   interactive modal appears — **Approve**, **Request Changes** or **Reject** with a comment.
4. Once code is generated, use `Preview` → **Run project** to start its GUI/API and interact
   with it inside DevForge; `Stop` shuts the preview server down. `Tests` and `Security` show
   complete report output and wrap long result text inside their own tabs. `Code`, `Docs` and
   `Audit` show the generated source, documentation and delivery history.
   The full project lives in `workspaces/{project_id}/` with its own git repo and CI workflow.
5. For a completed or failed project, choose **Request Changes** to replace its task and
   regenerate the project from scratch. The generated project includes a local browser GUI
   served with its API and can be run in the embedded Preview tab; prior audit and test history
   are retained.

### 4. Verify it yourself

```bash
# full pipeline, auto-approving every gate (requires backend on :8000)
python3 scripts/e2e_smoke.py

# existing-project regeneration guards
python3 scripts/test_regeneration.py

# decision-loop unit verification (reject loop, D4 self-heal, D5 fix loop)
backend/.venv/bin/python scripts/test_loops.py
```

---

## The 6-layer architecture (as implemented)

| Layer | Implementation |
|---|---|
| **Backend / API** | FastAPI async endpoints, Pydantic v2 models, **SSE** (`GET /api/projects/{id}/events`) for real-time agent output |
| **Agent orchestrator** | Explicit async **state machine** (`orchestrator/workflow_engine.py`): typed `WorkflowState`, human **interrupt gates** (asyncio.Event waits), bounded feedback loops, crash-safe resume (state persisted after every transition) |
| **Frontend workspace** | React + Vite + Tailwind + Lucide: multi-role views (Developer/Architect/Tester/PM), live pipeline tracker, interactive approval gates, streaming logs console, file-tree code viewer with syntax highlighting, test/security/doc panels, audit trail |
| **Database & storage** | SQLite via SQLAlchemy 2 (projects, workflow events = audit trail, approvals, test results, security findings) + `./workspaces/{project_id}/` file workspaces |
| **LLM engine** | Provider abstraction (`llm/client.py`): OpenAI, Groq, Anthropic via httpx; automatic fallback chain; deterministic offline **mock provider** that generates a browser GUI and CLI; lenient JSON extraction + one corrective re-prompt on parse/validation failure |
| **Execution sandbox** | `execution/runner.py`: `subprocess.run` (arg list, never shell, hard timeout, captured I/O) running **pytest** in the workspace and **bandit** (or a built-in **AST + regex scanner** fallback); `execution/git_service.py` for `git init`/commit + generated GitHub Actions CI |

### Agent fleet

| Agent | Input | Output | Gate |
|---|---|---|---|
| **RA** Requirement | task prompt (+ feedback on re-run) | structured SRS (functional reqs, user stories, acceptance criteria) → `requirements/requirements.md` | G1 |
| **AA** Architecture | approved SRS | tech stack, API schema, directory tree, module design → `architecture/*.md` + `api_schema.json` | G2 |
| **CA** Coding | approved architecture (modes: initial / heal / security) | complete runnable code → `src/`, `conftest.py`, `.gitignore` | G3 (skipped in self-heal loops) |
| **TA** Testing | code + specs | pytest suite → `tests/test_*.py`, then executes it | D4 loop: fail → CA heal (max 3) |
| **SA** Security | code | bandit/AST scan report; HIGH findings → CA fix | D5 loop: findings → CA fix (max 2) |
| **DocA** Documentation | all artifacts | `README.md`, `docs/api.md`, `docs/architecture.md` | G6 |
| **GitSync** Delivery | approved workspace | git init + commit on `main` + `.github/workflows/ci.yml` | — |

The D4 loop keeps the original generated test suite unchanged and reruns it after each
repair. The Coding Agent receives the failing tests, current implementation and pytest
diagnostics; if it returns no implementation changes, the workflow stops with an explicit
error instead of repeating the same failed run.

### Why the generated code is stdlib-only

The Coding Agent is hard-constrained (prompt) to use only the Python standard library so the
**execution sandbox can run the tests without installing anything** — this keeps the
self-healing loops deterministic and fast. The architecture itself is framework-agnostic
(the API dispatcher maps `(method, path, body) → handler` and can be mounted in FastAPI/Flask).

### Security scanning

* `bandit -r src -f json` when bandit is installed (it's in `requirements.txt`);
* otherwise the built-in **AST analyzer** catches: `eval`/`exec`, `os.system`,
  `subprocess … shell=True`, unsafe `pickle`, weak hashes (`md5`/`sha1`), `yaml.load`
  without SafeLoader, TLS `verify=False`, **hardcoded secrets** (regex) and
  **string-interpolated SQL**.
* **HIGH** severity blocks the pipeline and triggers the D5 fix loop; MEDIUM/LOW are
  reported as informational.

---

## LLM configuration

| Env | Meaning |
|---|---|
| `LLM_PROVIDER` | `auto` (default) · `openai` · `gemini` · `ollama` · `groq` · `anthropic` · `mock` |
| `OPENAI_API_KEY` / `GEMINI_API_KEY` / `OLLAMA_API_KEY` / `GROQ_API_KEY` / `ANTHROPIC_API_KEY` | keys for the real providers |
| `OPENAI_MODEL` / `GEMINI_MODEL` / `OLLAMA_MODEL` / `GROQ_MODEL` / `ANTHROPIC_MODEL` | model names (defaults: gpt-4o-mini / gemini-2.5-flash / gpt-oss:120b-cloud / llama-3-3-70b-versatile / claude-3-5-sonnet-latest) |

`auto` picks the first configured provider (OpenAI, then Gemini, Ollama, Groq and Anthropic) and
**falls back to the mock provider** when no key exists (a warning is logged, and the
provider in use is shown in the UI and on every snapshot). To choose Gemini when both
OpenAI and Gemini keys are configured, set `LLM_PROVIDER=gemini`; use `LLM_PROVIDER=openai`
to choose OpenAI. For Ollama Cloud, set `LLM_PROVIDER=ollama`, provide `OLLAMA_API_KEY`
from your Ollama account, and set `OLLAMA_MODEL` to a model available to that account.
With a real provider, agent output is requested as strict JSON
(`response_format: json_object` where supported), parsed leniently, validated against the
Pydantic schema, and **re-prompted once** with the validation errors if it fails.

## API reference (abridged)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | liveness + active LLM provider |
| `POST` | `/api/projects` | create project `{name, task}` |
| `GET` | `/api/projects` / `/{id}` | list / full snapshot (state, artifacts, files, events, test runs) |
| `POST` | `/api/projects/{id}/start` | start (or resume) the workflow |
| `GET` | `/api/projects/{id}/events` | **SSE** live event stream |
| `GET` | `/api/projects/{id}/files` / `files/content?path=` | workspace file tree / safe file read |
| `POST` | `/api/projects/{id}/approvals` | `{gate, decision: approved\|rejected\|changes_requested, comment}` |
| `GET` | `/api/projects/{id}/approvals/pending` | which gate is waiting |
| `POST` | `/api/projects/{id}/execution/retest` / `rescan` | re-run pytest / security scan on demand |
| `POST` | `/api/projects/{id}/execution/git/commit` | manual git delivery |
| `GET` | `/api/projects/{id}/execution/logs?limit=` | audit trail from DB |
| `DELETE` | `/api/projects/{id}` | delete project + workspace |

## Resilience notes

* Every state transition persists the full `WorkflowState` to SQLite → after a backend
  restart, in-flight projects are marked `interrupted` and **resume from the saved stage**
  via the Resume button.
* All generated file writes go through traversal-safe path helpers; subprocesses use argument
  lists with hard timeouts and never `shell=True`.
* Gate rejection, self-heal and fix loops are all bounded (`max_gate_iterations=3`,
  `max_test_heals=3`, `max_security_fixes=2`) so a stuck agent fails the workflow with a
  clear error instead of looping forever.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `port 8000 already in use` | stop the other process or change the port (update the Vite proxy target too) |
| workflow stuck at a gate | the modal may be hidden — check the amber "approval" badge in the pipeline, or `GET .../approvals/pending` |
| tests fail with a real LLM provider | expected — the D4 loop auto-heals up to 3×; afterwards the failure output is in the `Tests` tab and `Audit` trail |
| bandit `sarif` loader warning | harmless (optional export plugin); JSON output is unaffected |
| reset everything | stop servers, delete `devforge/devforge.db` and `devforge/workspaces/` |

## Extension roadmap (post-prototype)

* LangGraph port of the engine (the explicit state machine maps 1:1 to a StateGraph)
* Alembic migrations + Postgres for multi-user deployments
* WebSockets + diff view (generated-vs-approved), per-agent token/cost metering
* LLM-as-judge test-quality scoring, SAST (Semgrep) + SCA (pip-audit) in the security stage
* Real GitHub push + Actions trigger in the delivery stage
