# AI Dev Team Architecture

## Control plane

The platform is a deterministic Python control plane. Azure OpenAI responses are untrusted proposals; Pydantic schemas, the task state machine, permissions, approvals, and the Tool Gateway make authoritative decisions.

The primary flow is:

1. Orchestrator creates a project and four primary agents.
2. AgentRuntime builds bounded private/shared context and calls the Azure-only client.
3. TaskManager validates dependencies and state transitions.
4. Scheduler runs eligible isolated worktree tasks concurrently.
5. ToolGateway validates each proposed operation and delegates to filesystem, Git, or Docker services.
6. IntegrationManager validates branches and performs only approved merges.
7. QAManager runs sandboxed tests and persists evidence.
8. DeliveryManager writes the final report and artifact references.

## Persistence

SQLite is the MVP source of truth. Repository is a small transactional adapter with schema version tracking, WAL mode, typed JSON payloads, consistent backup/restore, and a ProjectRepositoryPort protocol for a future PostgreSQL adapter.

Logical state includes projects, agents, private/shared memory, tasks, dependencies, executions, messages, approvals, file ownership and locks, tool calls, audit events, checkpoints, artifacts, model usage, users, and sessions.

## Web dashboard

app.web.dashboard provides a dependency-free local HTTP dashboard. The browser receives read models and never receives Azure settings, database handles, model clients, or host filesystem authority. Mutating requests require an authenticated session, RBAC permission, and CSRF token.

## Browser QA

PlaywrightRunner writes evidence under data/artifacts/PROJECT-ID/. It runs a trusted browser worker in the configured Docker image, starts the generated app with an argv-only command, waits for readiness, captures deterministic desktop/tablet/mobile screenshots, traces, videos, console/network/browser diagnostics, HTML/JSON reports, and visual diffs. Baselines are never silently accepted as visual approval.

