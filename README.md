# AI Dev Team

AI Dev Team is a local, policy-controlled, multi-project software development
workspace. Create independent projects, describe an application in a
project-specific chat, review the Orchestrator's plan, and coordinate isolated
Planning, Frontend, Backend, and Testing agents. Each project has its own
chat, memory, tasks, Git workspace, artifacts, QA evidence, and application
preview.

The workspace is chat-first: the center panel is the project conversation and
the right panel renders the actual generated application. It includes Live
Preview, Final Application, QA Results, Screenshots, Agent Activity, and Build
Artifacts tabs.

The LLM proposes. Python decides. The platform intentionally does not use
LangChain, CrewAI, AutoGen, Semantic Kernel, or another agent framework, and
Azure OpenAI is the only model-provider boundary.

## How the platform works

Each project follows a deterministic, approval-controlled workflow:

1. The user creates a project and describes the application in the project
   chat.
2. The Python Orchestrator sends the requirement to the Planning Agent and
   persists the typed plan in SQLite.
3. The user approves or rejects the plan. Approval is required before the
   implementation stages begin.
4. The Frontend and Backend Agents work concurrently in separate Git worktrees
   using the Tool Gateway. Their task state, messages, memory, tool calls, and
   commits are recorded for that project.
5. The Testing Agent runs independent tests in the Docker sandbox. Failures
   create repair tasks and route work back to the responsible agent.
6. After integration approval, the Orchestrator merges the approved work,
   runs final QA, launches the isolated preview, and stores screenshots,
   reports, and delivery artifacts.

Every project has separate membership, chat history, agent memory, tasks,
workspaces, preview runtime, QA results, and artifacts. Switching projects in
the dashboard changes the complete context rather than only changing the
visible project name.

## Agents

The platform has four primary agents per project:

| Agent | Responsibility |
| --- | --- |
| Planning Agent | Turns the requirement into a typed, dependency-aware implementation plan. |
| Frontend Agent | Builds and changes the user interface and frontend assets. |
| Backend Agent | Builds APIs, server behavior, and backend integration. |
| Testing Agent | Independently tests the application, diagnoses failures, and proposes repair tasks. |

That means the normal project team contains four primary agents. The
Orchestrator is the deterministic coordinator, not a fifth autonomous coding
agent: it schedules tasks, enforces permissions, requests human approvals,
performs integration, and controls QA and delivery.

The architecture also supports dynamic sub-agents when a task needs them.
Sub-agents do not receive unrestricted access or independent authority. They
must be created through the Python runtime with an allowed role, scoped project
memory, authorized paths, permitted tools, token limits, and the parent task's
approval and ownership rules.

## Repository structure

```text
AI Dev Team/
├── app/
│   ├── ai/              Azure OpenAI client and structured/tool-call boundary
│   ├── agents/          Primary-agent definitions and permissions
│   ├── communication/   Persisted project message bus
│   ├── database/        SQLite repository, migrations, backups, and read models
│   ├── memory/          Private agent memory and shared project memory
│   ├── observability/   Metrics and monitoring read models
│   ├── orchestrator/    Deterministic planning, scheduling, integration, QA, delivery
│   ├── qa/              Docker-backed tests and Playwright browser QA
│   ├── runtime/         Agent execution loop and context construction
│   ├── schemas/         Typed Pydantic domain and tool models
│   ├── security/        Authentication, RBAC, CSRF, approvals, and audit logging
│   ├── tasks/           Task state machine and dependency scheduling
│   ├── tools/           File, Git, Docker, worktree, and Tool Gateway controls
│   └── web/             Authenticated dashboard, workspace APIs, and previews
├── projects/            Independent project Git repositories
├── workspaces/           Agent-specific Git worktrees
├── data/
│   ├── ai_dev_team.sqlite3  Project state, memory, chat, tasks, and audit data
│   └── artifacts/            QA reports, screenshots, traces, and delivery files
├── docker/              Pinned sandbox and Playwright image definitions
├── tests/               Unit, security, API, integration, and persistence tests
├── PRD.md               Product and security requirements
├── ARCHITECTURE.md      Detailed component and data-flow design
└── IMPLEMENTATION_STATUS.md  Verified milestones and test evidence
```

Generated applications normally contain their own `frontend/`, `backend/`,
and `tests/` directories inside `projects/<PROJECT_ID>/`. The platform keeps
those files isolated from the control-plane source under `app/`.

## Quick start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
```

Configure the Azure OpenAI settings in `.env`. Azure OpenAI is the only model
provider; credentials stay in the trusted host process and are never sent to
the browser or generated-code containers.

### Start the web workspace

Set the first administrator explicitly without committing credentials:

```bash
export AI_DEV_TEAM_ADMIN_USERNAME=admin
export AI_DEV_TEAM_ADMIN_PASSWORD='use-a-local-password-at-least-12-characters'
python3 -m app.main dashboard
```

Open [http://127.0.0.1:8080/](http://127.0.0.1:8080/) and sign in. The
dashboard supports project search, isolated project creation, persistent chat,
approval decisions, agent activity, and responsive layouts. Do not place real
secrets in this README or in browser JavaScript.

### Chat-driven workflow

1. Create a project and describe the application in its chat.
2. Review and approve the generated plan.
3. Let the Frontend, Backend, and Testing agents execute their approved tasks.
4. Review repair tasks, integration approval, QA results, screenshots, and
   delivery artifacts in the same project workspace.
5. View the running application in the Live Preview tab. Preview containers
   use read-only project mounts, non-root execution, resource limits, and a
   host-loopback-only published port.

The CLI remains available for deterministic operations and recovery:

```bash
ai-dev-team create "Example app" "Build a small task tracker with a JSON API and responsive web UI."
```

Projects are stored under `projects/`, isolated worktrees under `workspaces/`,
SQLite state under `data/`, and delivery artifacts under `data/artifacts/`.

```bash
ai-dev-team plan PROJECT-...
ai-dev-team request-approval PROJECT-...
ai-dev-team decide APPROVAL-... human-user approve
ai-dev-team run PROJECT-...
ai-dev-team request-integration PROJECT-...
ai-dev-team decide APPROVAL-... human-user approve
ai-dev-team integrate PROJECT-...
ai-dev-team qa PROJECT-...
ai-dev-team deliver PROJECT-...
ai-dev-team status PROJECT-...
ai-dev-team dashboard
```

The dashboard binds to `127.0.0.1:8080` by default. Set
`AI_DEV_TEAM_ADMIN_USERNAME` and a 12+ character
`AI_DEV_TEAM_ADMIN_PASSWORD` explicitly to bootstrap the first admin. The
browser receives only derived project data; Azure credentials remain in the
trusted host process.

## Security boundaries

- Agent output is untrusted and validated with Pydantic before use.
- Agents never access SQLite, Git, Docker, or the host shell directly.
- File operations require canonical-path, symlink-escape, ownership, lock,
  task, and tool-allowlist checks in the Python Tool Gateway.
- Code execution uses Docker with a non-root user, dropped capabilities,
  read-only root filesystem, resource limits, and `--network=none` by default.
- Development agents use Git worktrees; agents cannot merge directly to main.
- Plan, shared/protected file, network, secret, destructive, merge, and release
  actions are approval-gated.
- Project membership checks prevent users from reading or modifying another
  project's chat, tasks, memory, workspaces, previews, or artifacts.
- Preview ports are published only on `127.0.0.1`; arbitrary public container
  ports and Docker-socket access are not exposed.

## Verification

```bash
pytest
ruff check app tests
mypy app
bandit -c .bandit -r app
python3 -m compileall -q app
```

The verified Phase 3 checkpoint includes 23 passing Python tests and an
isolated Playwright acceptance run with 66 passing workflow actions across
desktop, tablet, and mobile viewports. The real generated application preview
also passed a Docker-backed `/health` check through a loopback-only port.

See `PRD.md` for the complete product contract and
`IMPLEMENTATION_STATUS.md` for verified implementation checkpoints.

Operational details are documented in `ARCHITECTURE.md`, `SECURITY.md`,
`API_DOCUMENTATION.md`, `DEPLOYMENT.md`, and `QA_DOCUMENTATION.md`.
