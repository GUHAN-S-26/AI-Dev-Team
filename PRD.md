# AI Dev Team

## Product Requirements Document (PRD)

  Field                    Value
  ------------------------ ----------------------------------
  Product name             AI Dev Team
  Document type            Product Requirements Document
  Version                  2.0
  Status                   Revised Draft
  Primary language         Python
  AI provider              Azure OpenAI only
  Architecture             Custom multi-agent orchestration
  Agent framework policy   No agent frameworks
  Initial persistence      SQLite
  Execution isolation      Docker + Git worktrees

------------------------------------------------------------------------

## 1. Executive Summary

AI Dev Team is an autonomous, policy-controlled software development
platform. A user submits a software requirement in natural language. The
platform analyzes the requirement, creates an approved architecture and
implementation plan, assigns work to specialized agents, develops
frontend and backend components concurrently where dependencies permit,
executes tests, coordinates fixes, integrates validated changes, and
delivers the application with documentation and a quality report.

The platform consists of a deterministic Python orchestrator and four
primary AI agents:

1.  Planning Agent
2.  Frontend Agent
3.  Backend Agent
4.  Testing Agent

Primary agents may request bounded, task-specific sub-agents. All agent
communication, tool execution, state changes, memory writes, file
operations, and integration actions are mediated by deterministic Python
services.

**Core principle:** Agents are reasoning components, not trusted
execution components. LLM output is untrusted input. Deterministic
services enforce authorization, workflow state, resource limits,
validation, and auditability.

## 2. Product Vision and Goals

### 2.1 Vision

Provide a virtual software engineering team that can take a well-scoped
product requirement from initial analysis to a tested, documented,
reviewable application while preserving human control over high-impact
decisions.

### 2.2 Primary goals

-   Implement a custom multi-agent architecture in Python without an
    agent framework.
-   Use Azure OpenAI as the only model provider.
-   Support four independent primary agents and bounded sub-agents.
-   Maintain private agent memory and approved shared project memory.
-   Decompose projects into dependency-aware tasks.
-   Run independent tasks concurrently.
-   Enforce file ownership and tool permissions in Python services.
-   Isolate code execution using Docker.
-   Isolate parallel Git work using branches and worktrees.
-   Generate frontend and backend implementation code.
-   Generate and execute unit, API, integration, and end-to-end tests.
-   Coordinate bug-fix and regression cycles.
-   Persist execution history and recover from process interruption.
-   Deliver source code, documentation, test results, and a final
    report.

### 2.3 Non-goals for the initial release

-   Multiple AI providers or automatic provider fallback.
-   LangChain, CrewAI, AutoGen, Semantic Kernel, or similar agent
    frameworks.
-   Unrestricted host operating-system access.
-   Unrestricted network access from execution containers.
-   Unlimited or recursively unbounded agent creation.
-   Direct agent merges into the main branch.
-   Automatic production deployment without explicit human approval.
-   Automatic modification of files outside an agent's authorized
    workspace.
-   Training or fine-tuning foundation models.
-   A general-purpose public multi-tenant SaaS service in the first MVP.

## 3. Users and Core Use Cases

### 3.1 Primary user

A software developer, technical founder, engineering team, or researcher
who wants to turn a software specification into a working codebase with
controlled autonomous assistance.

### 3.2 Core use cases

1.  Submit a new application requirement.
2.  Review and approve the proposed requirements, architecture,
    contracts, and task plan.
3.  Allow frontend and backend work to proceed concurrently when safe.
4.  Inspect agent progress, task status, tool activity, and execution
    logs.
5.  Review proposed architecture or API contract changes.
6.  Inspect and approve integration of validated code.
7.  Review test failures and coordinated fixes.
8.  Resume a project after an interruption.
9.  Export the completed project and its documentation.

## 4. Product Principles

-   **Deterministic control plane:** The orchestrator and policy
    services make authoritative decisions.
-   **Least privilege:** Each agent receives only the permissions and
    tools needed for its task.
-   **Untrusted model output:** Every model response and tool request is
    parsed, validated, and authorized.
-   **Contract-first parallelism:** Frontend and backend agents work
    independently against approved contracts.
-   **Independent QA:** The Testing Agent reports defects but does not
    silently alter application source.
-   **Traceability:** Every task, message, approval, tool call, file
    change, and merge is recorded.
-   **Recoverability:** Workflow state is persisted so interrupted work
    can resume safely.
-   **Human control:** Sensitive actions and release decisions require
    explicit approval.
-   **Bounded autonomy:** Model calls, retries, sub-agents, execution
    time, tokens, and costs have configurable limits.

## 5. Technology Stack

  Component             Technology
  --------------------- -------------------------------------------------
  Language              Python 3.12+
  AI provider           Azure OpenAI only
  AI SDK                Official OpenAI Python SDK configured for Azure
  Data validation       Pydantic
  Async execution       asyncio
  Persistence           SQLite for MVP
  Future persistence    PostgreSQL
  Database access       SQLAlchemy or a small repository layer
  Version control       Git
  Parallel workspaces   Git worktrees
  Code execution        Docker
  Backend tests         pytest
  API tests             pytest + requests or httpx
  Browser tests         Playwright
  Static checks         Ruff, mypy, Bandit, and project-specific checks
  Configuration         Environment variables and validated settings
  Logging               Python logging with structured JSON output
  API contracts         OpenAPI where applicable
  Packaging             pyproject.toml

No agent framework may be introduced. Ordinary libraries for HTTP,
validation, persistence, testing, and container management are
permitted.

## 6. System Architecture

### 6.1 Major components

1.  **Project Orchestrator:** Deterministic workflow controller.
2.  **Agent Runtime:** Loads agent instructions, task context, memory,
    and tool definitions; invokes Azure OpenAI; validates model output.
3.  **Primary Agents:** Planning, Frontend, Backend, and Testing.
4.  **Sub-Agent Manager:** Validates and creates bounded task-specific
    sub-agents.
5.  **Task Manager:** Stores tasks, dependencies, owners, priorities,
    and state transitions.
6.  **Message Bus:** Persists and routes structured agent messages.
7.  **Memory Manager:** Maintains private agent memory and approved
    project memory.
8.  **Tool Gateway:** Authorizes and executes all agent-requested tools.
9.  **Permission Manager:** Enforces file ownership, task authorization,
    tool permissions, and resource policies.
10. **Workspace Manager:** Creates and manages Git worktrees and task
    workspaces.
11. **Sandbox Manager:** Executes commands and tests in restricted
    Docker containers.
12. **Integration Manager:** Validates branches and controls merges.
13. **QA Manager:** Coordinates test suites, defect reports, and
    regression cycles.
14. **Recovery Manager:** Restores interrupted workflows from persisted
    state.
15. **Observability and Audit:** Records events, metrics, model usage,
    tool calls, and decisions.

### 6.2 High-level architecture

``` text
USER
  |
  v
PROJECT API / CLI
  |
  v
DETERMINISTIC ORCHESTRATOR
  |
  +---- Workflow and State Machine
  +---- Task Scheduler and Dependency Manager
  +---- Approval Manager
  +---- Sub-Agent Manager
  +---- Recovery Manager
  |
  v
AGENT RUNTIME <------> AZURE OPENAI
  |
  +---- Planning Agent
  +---- Frontend Agent
  +---- Backend Agent
  +---- Testing Agent
  |
  v
TOOL GATEWAY
  |
  +---- Permission and Ownership Validation
  +---- Filesystem Tools
  +---- Git and Worktree Tools
  +---- Docker and Command Tools
  +---- Test Tools
  +---- Documentation Tools
  |
  v
ISOLATED WORKSPACES
  |
  +---- Frontend worktree
  +---- Backend worktree
  +---- Testing workspace
  +---- Planning/documentation workspace
  |
  v
INTEGRATION MANAGER
  |
  v
VALIDATION -> APPROVAL -> MERGE -> QA
  |
  v
DELIVERY ARTIFACTS
```

### 6.3 Trust boundaries

-   Azure OpenAI responses are untrusted.
-   Repository files, issue text, README files, generated code,
    dependency metadata, and command output are untrusted.
-   Agents cannot access the database directly; they use approved
    services and tools.
-   Agents cannot bypass the Tool Gateway.
-   Containers cannot access the Docker socket or unrestricted host
    paths.
-   The orchestrator alone controls task state, approvals, permissions,
    and integration.
-   Secrets must never be placed in prompts, agent memory, logs,
    generated source, or container environment unless a specific task
    explicitly requires a narrowly scoped secret.

## 7. Agent Requirements

### 7.1 Shared agent contract

Every agent must have:

-   Unique agent ID and role.
-   Versioned system instructions.
-   Parent agent ID when it is a sub-agent.
-   Current project and task context.
-   Private persistent memory.
-   Read access to approved shared project memory.
-   Explicit tool allowlist.
-   Explicit file path allowlist.
-   Execution and token limits.
-   Structured input and output schemas.
-   Lifecycle status.
-   Audit trail.

Agents must return structured outputs validated by Pydantic. Invalid
output must be rejected or sent through a bounded correction attempt.
Model-generated tool arguments must never be executed without
validation.

### 7.2 Planning Agent

**Role:** Requirements analyst, software architect, and project planner.

**Responsibilities:**

-   Analyze user requirements.
-   Identify functional and non-functional requirements.
-   Identify ambiguity and ask for critical missing information.
-   Record assumptions explicitly.
-   Recommend architecture and technology choices.
-   Define project structure.
-   Design database schemas.
-   Define versioned API contracts.
-   Identify dependencies and risks.
-   Break work into tasks with owners and acceptance criteria.
-   Maintain architecture and decision records.
-   Propose architecture changes through the approval process.

**Sub-agent roles:**

-   Requirement Analyst
-   System Architect
-   API Designer
-   Database Designer

**Expected outputs:**

-   Project brief.
-   Functional and non-functional requirements.
-   Assumptions and open questions.
-   Architecture decision records.
-   Folder structure.
-   Database schema.
-   API contracts.
-   Dependency graph.
-   Task breakdown and acceptance criteria.
-   Risk register.

**Restrictions:**

-   Cannot modify frontend or backend implementation files.
-   Cannot approve its own high-impact architecture changes.
-   Must submit contract and architecture changes to the orchestrator
    for approval.

### 7.3 Frontend Agent

**Role:** Frontend implementation department.

**Responsibilities:**

-   Initialize frontend project.
-   Build pages, layouts, and reusable components.
-   Implement navigation and state management.
-   Implement forms and client-side validation.
-   Integrate approved backend APIs.
-   Handle loading, empty, and error states.
-   Implement responsive behavior and accessibility.
-   Write frontend tests.
-   Maintain frontend documentation.

**Sub-agent roles:**

-   UI Developer
-   Component Developer
-   Integration Developer
-   UI Reviewer

**Expected outputs:**

-   Frontend source code.
-   Reusable components.
-   Application pages.
-   API integration.
-   Frontend tests.
-   Build and development documentation.

**Restrictions:**

-   Cannot modify backend source.
-   Cannot independently change approved API contracts.
-   Cannot write outside authorized frontend paths.
-   Must request shared-file or contract changes through the
    orchestrator.

### 7.4 Backend Agent

**Role:** Backend implementation department.

**Responsibilities:**

-   Initialize backend project.
-   Implement APIs and business logic.
-   Implement data models and migrations.
-   Implement authentication and authorization.
-   Validate input and output.
-   Handle exceptions and logging.
-   Implement security controls.
-   Write unit and API tests.
-   Maintain API and backend documentation.

**Sub-agent roles:**

-   API Developer
-   Database Developer
-   Security Developer
-   Business Logic Developer

**Expected outputs:**

-   Backend source code.
-   API endpoints.
-   Database models and migrations.
-   Authentication and authorization.
-   Backend tests.
-   API documentation.

**Restrictions:**

-   Cannot modify frontend source.
-   Cannot independently change approved API contracts.
-   Cannot write outside authorized backend paths.
-   Must document schema and contract changes.

### 7.5 Testing Agent

**Role:** Independent quality assurance department.

**Responsibilities:**

-   Analyze acceptance criteria.
-   Create test strategy and test cases.
-   Generate unit, API, integration, and end-to-end tests.
-   Execute tests in approved sandboxes.
-   Analyze failures and distinguish product defects from environment
    failures.
-   Create structured bug reports and repair tasks.
-   Verify fixes and run regression tests.
-   Validate final acceptance criteria.
-   Produce final QA report.

**Sub-agent roles:**

-   Unit Testing Agent
-   API Testing Agent
-   Integration Testing Agent
-   Regression Testing Agent

**Expected outputs:**

-   Test plan.
-   Test cases.
-   Test execution reports.
-   Defect reports.
-   Regression reports.
-   Final QA report.

**Restrictions:**

-   Cannot modify frontend or backend implementation source.
-   May modify files in its authorized test workspace.
-   Must route defects to the responsible development agent.
-   Test results must include reproducible evidence where possible.

## 8. Orchestrator Requirements

The orchestrator is deterministic Python code, not an autonomous AI
agent.

### 8.1 Responsibilities

-   Receive and validate project requests.
-   Create project records and workspaces.
-   Initialize primary agents.
-   Invoke requirement analysis and planning.
-   Validate plan completeness.
-   Request human approval where required.
-   Create and assign tasks.
-   Validate task dependencies.
-   Schedule eligible tasks concurrently.
-   Enforce concurrency and resource limits.
-   Route messages.
-   Enforce permissions.
-   Monitor agent and task health.
-   Handle retries and timeouts.
-   Coordinate integration.
-   Trigger test suites.
-   Coordinate bug-fixing loops.
-   Persist checkpoints.
-   Resume recoverable workflows.
-   Produce final delivery report.

### 8.2 Workflow

``` text
REQUEST RECEIVED
      |
      v
REQUIREMENT ANALYSIS
      |
      v
PLAN AND ARCHITECTURE GENERATED
      |
      v
PLAN VALIDATION
      |
      v
HUMAN APPROVAL GATE
      |
      v
TASK GRAPH CREATED
      |
      v
DEPENDENCY-AWARE SCHEDULING
      |
      +-----------------------+
      |                       |
      v                       v
FRONTEND DEVELOPMENT    BACKEND DEVELOPMENT
      |                       |
      +-----------+-----------+
                  |
                  v
          BRANCH VALIDATION
                  |
                  v
          INTEGRATION REVIEW
                  |
                  v
          APPROVED INTEGRATION
                  |
                  v
             QA EXECUTION
                  |
             +----+----+
             |         |
            PASS       FAIL
             |         |
             v         v
          DELIVERY   DEFECT TASKS
                        |
                        v
                  FIX AND RETEST
                        |
                        v
                  REGRESSION QA
```

### 8.3 Scheduling rules

-   A task is eligible only when all dependencies are completed and
    approved.
-   Independent tasks may execute concurrently.
-   A task must have exactly one accountable owner at a time.
-   Concurrency is configurable globally and per agent.
-   Conflicting file scopes must not run concurrently unless isolated
    and explicitly approved.
-   Scheduling must be deterministic given the same persisted state and
    policy configuration.
-   The scheduler must avoid deadlocks and detect dependency cycles
    before execution.

## 9. Task Management and State Machine

### 9.1 Task schema

``` json
{
  "task_id": "TASK-001",
  "project_id": "PROJECT-001",
  "title": "Create login API",
  "description": "Implement the approved user login endpoint",
  "assigned_agent": "backend",
  "parent_task_id": null,
  "priority": "high",
  "status": "PENDING",
  "dependencies": [],
  "acceptance_criteria": [
    "Accept email and password",
    "Validate credentials",
    "Return an access token",
    "Handle invalid credentials safely"
  ],
  "created_at": null,
  "updated_at": null
}
```

### 9.2 Task statuses

-   PENDING
-   ASSIGNED
-   IN_PROGRESS
-   BLOCKED
-   REVIEW
-   COMPLETED
-   FAILED
-   CANCELLED

### 9.3 Transition rules

``` text
PENDING -> ASSIGNED -> IN_PROGRESS
IN_PROGRESS -> BLOCKED -> IN_PROGRESS
IN_PROGRESS -> REVIEW
REVIEW -> COMPLETED
REVIEW -> IN_PROGRESS
IN_PROGRESS -> FAILED
FAILED -> PENDING (bounded retry only)
PENDING -> CANCELLED
ASSIGNED -> CANCELLED
```

All transitions must be validated by the Task Manager. Agents may
request a transition but cannot directly update authoritative task
state.

### 9.4 Task execution records

A task and each attempt must be separate records. Retrying a task must
preserve prior attempts, logs, model usage, tool calls, outputs, and
errors.

Each execution record must include:

-   Execution ID.
-   Task ID and attempt number.
-   Agent ID.
-   Start and end timestamps.
-   Status.
-   Input and output references.
-   Tool-call references.
-   Token and cost estimates.
-   Error classification.
-   Workspace and commit references.

## 10. Sub-Agent Management

### 10.1 Creation

Primary agents may request sub-agent creation. The Sub-Agent Manager
validates the request before creation.

### 10.2 Limits

Initial defaults:

-   Maximum hierarchy depth: 2 below the orchestrator.
-   Maximum active sub-agents per primary agent: 3.
-   Maximum concurrent tasks: configurable.
-   Maximum retries per task: 3.
-   Maximum model calls and token budget per task: configurable.
-   Maximum total project budget: configurable.

### 10.3 Required properties

-   Agent ID.
-   Parent agent ID.
-   Role and instructions.
-   Project ID.
-   Task ID.
-   Private memory namespace.
-   Authorized paths.
-   Tool allowlist.
-   Execution limits.
-   Status and timestamps.

### 10.4 Lifecycle

``` text
REQUESTED -> VALIDATED -> CREATED -> ASSIGNED
     -> RUNNING -> OUTPUT_VALIDATION -> REPORTED
     -> MEMORY_COMMITTED -> COMPLETED
```

Rejected requests must include a reason. A sub-agent cannot create
another sub-agent in the initial release.

## 11. Memory Management

### 11.1 Memory categories

**Private agent memory**

Stores role-specific lessons, prior task summaries, decisions, known
issues, and useful code references.

**Shared project memory**

Stores approved requirements, architecture, contracts, project
structure, decisions, and current project status.

**Task and execution history**

Stores task assignments, attempts, outputs, failures, communications,
approvals, tool calls, and workflow events.

### 11.2 Storage policy

SQLite is the source of truth in the MVP. JSON is used for validated
structured payloads, import/export, and memory snapshots, not as a
second competing persistence system.

Suggested logical tables:

-   projects
-   agents
-   agent_memory
-   project_memory
-   memory_events
-   tasks
-   task_dependencies
-   executions
-   messages
-   approvals
-   file_ownership
-   file_locks
-   tool_calls
-   audit_events
-   workflow_checkpoints
-   artifacts
-   model_usage

### 11.3 Memory rules

-   Every agent and sub-agent has a private memory namespace.
-   Agents can read only their own private memory and approved shared
    memory.
-   Agents cannot directly overwrite another agent's private memory.
-   All memory writes pass through Memory Manager.
-   Memory updates include project ID, agent ID, timestamp, source task,
    and schema version.
-   Retrieve only task-relevant memory.
-   Do not send complete memory history to Azure OpenAI.
-   Store references to code and artifacts rather than duplicating large
    files in memory.
-   Support retention limits and project-level memory export.
-   Never store secrets, credentials, or sensitive tokens in memory.

## 12. Agent Communication

### 12.1 Message bus

All agent communication passes through a persisted central Message Bus.
Direct uncontrolled agent-to-agent communication is prohibited.

### 12.2 Message schema

``` json
{
  "message_id": "MSG-001",
  "from_agent": "planning",
  "to_agent": "backend",
  "project_id": "PROJECT-001",
  "task_id": "TASK-001",
  "message_type": "TASK_ASSIGNMENT",
  "content": {
    "description": "Implement the approved login API"
  },
  "status": "PENDING",
  "created_at": null
}
```

### 12.3 Message types

-   TASK_ASSIGNMENT
-   TASK_COMPLETED
-   TASK_FAILED
-   APPROVAL_REQUIRED
-   BUG_FOUND
-   CONTRACT_UPDATED
-   DEPENDENCY_BLOCKED
-   SUB_AGENT_REQUEST
-   REVIEW_REQUEST
-   REVIEW_COMPLETED
-   TOOL_REQUEST
-   TOOL_RESULT
-   CONTEXT_REQUEST

Messages must be schema-validated, persisted, timestamped, and
correlated to a project and task where applicable. Delivery must be
idempotent.

## 13. Tool Gateway and Execution Runtime

### 13.1 Purpose

The Tool Gateway is the only supported route for agent-requested
operations that affect files, processes, Git repositories, containers,
tests, or project state.

### 13.2 Tool invocation lifecycle

1.  Parse model tool request.
2.  Validate tool name and argument schema.
3.  Resolve agent, project, task, and workspace identity.
4.  Check tool allowlist.
5.  Check path ownership and task authorization.
6.  Check locks and conflicting operations.
7.  Apply resource and network policy.
8.  Execute in the approved environment.
9.  Capture output and exit status.
10. Persist audit record and return a bounded result.

### 13.3 Initial tool catalog

-   Read file.
-   List authorized directory.
-   Create file.
-   Modify file.
-   Delete file.
-   Search authorized workspace.
-   Run approved command.
-   Run formatter and linter.
-   Run test suite.
-   Create Git branch or worktree.
-   Commit changes.
-   Generate diff.
-   Request merge.
-   Read approved project artifact.

Tools must use typed arguments and bounded output sizes. Shell access
must be restricted to an explicit command policy; do not expose an
unrestricted host shell.

## 14. Workspace, File Ownership, and Conflict Prevention

### 14.1 Git isolation

Each primary development agent uses an isolated Git worktree or
equivalent task workspace.

Initial logical branches:

``` text
main
├── planning
├── frontend
├── backend
└── testing
```

Sub-agents working concurrently on overlapping scopes must receive
separate worktrees or task branches.

### 14.2 Ownership registry

Example:

``` json
{
  "planning": ["docs/**", "architecture/**"],
  "frontend": ["frontend/**"],
  "backend": ["backend/**"],
  "testing": ["tests/**"]
}
```

The actual registry must be project-configurable and support explicit
shared-file ownership.

### 14.3 File operation authorization

Before every create, read, modify, move, or delete operation:

1.  Resolve the canonical target path.
2.  Reject path traversal and symlink escapes.
3.  Identify agent, project, task, and workspace.
4.  Check agent tool permissions.
5.  Check file ownership and task authorization.
6.  Check file locks and concurrent operations.
7.  Check whether the path is a protected shared file.
8.  Execute only inside the authorized workspace.
9.  Record the operation and result.

Path checks must be enforced by Python code and
operating-system/container boundaries, not by prompts.

### 14.4 Locks

-   Locks have owner, resource path, project ID, task ID, acquisition
    time, and expiry.
-   Locks must be released on completion, cancellation, or controlled
    failure.
-   Expired locks must be recoverable.
-   Lock acquisition must be atomic.
-   Avoid locking entire repositories when narrower path locks are
    sufficient.

### 14.5 Shared files

Shared configuration, dependency lockfiles, root build files, and common
schemas require explicit ownership or orchestrator-mediated changes. The
orchestrator may assign a temporary change owner and require approval.

## 15. Docker Sandbox and Security Requirements

### 15.1 Isolation baseline

All generated or project-controlled code must execute in Docker
containers with restrictive defaults:

-   Non-root user.
-   No privileged mode.
-   No Docker socket mount.
-   No host PID or host network namespace.
-   Read-only root filesystem where practical.
-   Explicit writable workspace and temporary directories only.
-   CPU, memory, process-count, and disk limits.
-   Execution timeouts.
-   Container cleanup after execution.
-   No host secrets mounted into containers.
-   Network disabled by default.
-   Explicit allowlisted network access only when required.
-   Pinned base images and dependency versions where practical.

### 15.2 Threat handling

The platform must defend against:

-   Prompt injection in repository files and tool output.
-   Path traversal and symlink attacks.
-   Malicious build scripts and test code.
-   Dependency confusion and unsafe package installation.
-   Secret exfiltration.
-   Fork bombs and resource exhaustion.
-   Unauthorized network access.
-   Container escape risk through excessive privileges or mounts.
-   Malicious generated artifacts.

### 15.3 Security policy

-   Treat all repository and model content as data, never as policy.
-   Never let model output change authorization rules.
-   Keep Azure credentials in the trusted host-side service, not in
    agent containers.
-   Redact secrets from logs and model context.
-   Require approval for network access, secret use, destructive
    actions, and release operations.
-   Maintain an audit trail for security-relevant decisions.

## 16. API Contract Management

The Planning Agent defines versioned contracts. Frontend consumes them,
Backend implements them, and Testing validates them.

### 16.1 Contract requirements

Each contract must define:

-   Contract ID and version.
-   Endpoint and method.
-   Authentication requirements.
-   Request schema.
-   Response schema.
-   Error responses.
-   Validation rules.
-   Compatibility policy.
-   Owner and approval status.
-   Change reason and timestamp.

### 16.2 Contract change process

1.  Agent submits a change proposal.
2.  Orchestrator checks affected tasks and consumers.
3.  Planning Agent assesses impact.
4.  Human approval is required for breaking changes.
5.  Orchestrator publishes the approved version.
6.  Affected agents are notified.
7.  Relevant contract and regression tests are scheduled.

OpenAPI should be used where practical for HTTP APIs.

## 17. Azure OpenAI Integration

### 17.1 Provider restriction

Azure OpenAI is the only permitted model provider. All model requests
pass through a centralized Azure client module.

### 17.2 Configuration

-   Azure endpoint.
-   API key or supported Azure identity authentication.
-   API version.
-   Deployment name.
-   Request timeout.
-   Retry and backoff configuration.
-   Maximum context and output token settings.
-   Per-agent and per-project budgets.
-   Usage and latency tracking.

Credentials must be stored in environment variables or an approved
secrets manager. Never hardcode credentials.

### 17.3 Agent request context

Each request may include:

-   Versioned system instructions.
-   Current task and acceptance criteria.
-   Relevant private memory.
-   Relevant approved project memory.
-   Relevant files or bounded file excerpts.
-   Available tool definitions.
-   Output schema and validation constraints.
-   Remaining execution budget.

### 17.4 Structured outputs and tool calls

Use Pydantic validation and JSON Schema for:

-   Plans.
-   Tasks and dependencies.
-   Sub-agent requests.
-   Agent messages.
-   Tool arguments.
-   Bug reports.
-   Test reports.
-   Approval requests.
-   Final project reports.

Tool calls must be treated as proposals. The Tool Gateway performs
authorization and execution independently of the model.

### 17.5 Reliability and cost controls

-   Use bounded retries with exponential backoff and jitter.
-   Distinguish rate limits, transient service errors, invalid requests,
    and model-output errors.
-   Enforce request timeouts.
-   Track prompt tokens, completion tokens, latency, deployment, and
    estimated cost where pricing data is available.
-   Enforce per-task and per-project budgets.
-   Stop or request approval when a budget is exhausted.
-   Avoid retrying non-retryable failures.

## 18. Testing and Quality Assurance

### 18.1 Test levels

-   Unit tests.
-   Static analysis and type checks.
-   API contract tests.
-   Backend integration tests.
-   Database migration tests.
-   Frontend component tests where applicable.
-   Browser-based end-to-end tests using Playwright.
-   Security checks.
-   Regression tests.

### 18.2 Test timing

-   Testing Agent may create test specifications during planning.
-   Developers may create and run local unit tests during
    implementation.
-   Contract tests run when the relevant API implementation is
    available.
-   Full integration and end-to-end tests wait until components are
    integrated.
-   Regression tests run after fixes and approved integration changes.

### 18.3 Bug report schema

Each defect must include:

-   Bug ID.
-   Project and related task IDs.
-   Severity and priority.
-   Environment and commit reference.
-   Reproduction steps.
-   Expected behavior.
-   Actual behavior.
-   Logs, screenshots, or test evidence where available.
-   Suspected component.
-   Assigned owner.
-   Verification status.

### 18.4 Bug-fixing loop

-   Testing Agent creates a defect report.
-   Orchestrator validates and creates a repair task.
-   Responsible development agent receives the task.
-   Agent fixes the defect in its isolated workspace.
-   Automated checks run.
-   Integration Manager reviews the change.
-   Testing Agent verifies the fix and runs relevant regression tests.
-   Orchestrator stops after configured iteration limits and escalates
    unresolved issues.

## 19. Integration and Merge Management

The Integration Manager is a deterministic subsystem controlled by the
orchestrator.

### 19.1 Integration pipeline

1.  Confirm task completion and acceptance evidence.
2.  Verify branch and workspace identity.
3.  Validate file ownership.
4.  Generate and inspect diff.
5.  Run formatting, linting, type checks, and security checks.
6.  Run relevant unit and contract tests.
7.  Check for prohibited files, secrets, and unexpected changes.
8.  Request human review where policy requires it.
9.  Merge approved changes.
10. Record merge commit and validation evidence.
11. Trigger integration and regression testing.

### 19.2 Merge rules

-   Agents cannot merge directly into main.
-   No unvalidated code may enter main.
-   Merge operations are performed by the Integration Manager.
-   Conflicts must be resolved in a controlled integration workspace.
-   The system must preserve pre-merge commits and support rollback to
    the last known good integration point.
-   Failed integration must not silently mark tasks completed.

## 20. Human Approval and Governance

The following actions require explicit approval by default:

-   Approving the initial architecture and task plan.
-   Breaking API contract changes.
-   Changes to shared or protected files.
-   Adding new execution tools or permissions.
-   Enabling network access for a task.
-   Providing secrets to a task.
-   Destructive database or filesystem operations.
-   Merging to the main branch when configured as a protected action.
-   Production deployment or release.

Approval records must include approver identity, decision, scope,
timestamp, and relevant artifact or diff reference.

## 21. Recovery, Checkpointing, and Idempotency

### 21.1 Checkpoints

Persist workflow checkpoints after meaningful transitions, including:

-   Plan approval.
-   Task creation and assignment.
-   Task execution start and completion.
-   Agent output validation.
-   Sub-agent lifecycle transitions.
-   Integration stages.
-   Test suite completion.
-   Bug-fix iteration completion.
-   Delivery generation.

### 21.2 Recovery behavior

On restart, the orchestrator must:

1.  Load the latest valid project checkpoint.
2.  Reconcile task and execution states.
3.  Identify abandoned executions.
4.  Inspect worktree and container state.
5.  Expire stale locks safely.
6.  Preserve completed work.
7.  Retry only eligible interrupted tasks.
8.  Avoid duplicate commits, messages, or artifact publication.

Operations that may be repeated must use idempotency keys or equivalent
deduplication.

## 22. Observability, Audit, and Reporting

### 22.1 Logging

Use structured logs with:

-   Timestamp.
-   Project ID.
-   Agent ID.
-   Task ID.
-   Execution ID.
-   Correlation ID.
-   Event type.
-   Severity.
-   Duration.
-   Error classification.

Do not log secrets or full sensitive prompts by default.

### 22.2 Metrics

Track:

-   Tasks by status.
-   Task completion and failure rates.
-   Retry counts.
-   Agent execution time.
-   Queue wait time.
-   Model latency.
-   Token usage and estimated cost.
-   Tool-call counts and failures.
-   Test pass/fail rates.
-   Integration failures.
-   Sub-agent creation counts.
-   Recovery events.

### 22.3 Final delivery report

The platform must generate:

-   Project summary.
-   Delivered features.
-   Architecture summary.
-   Source branch and commit references.
-   Build and run instructions.
-   Test suites executed and results.
-   Known issues and limitations.
-   Security checks performed.
-   Outstanding approvals.
-   Artifact locations.
-   Model usage and execution summary.

## 23. Non-Functional Requirements

  -----------------------------------------------------------------------
  Category                            Requirement
  ----------------------------------- -----------------------------------
  Security                            Enforce least privilege and sandbox
                                      isolation

  Reliability                         Persist workflow and execution
                                      state

  Recoverability                      Resume from valid checkpoints

  Scalability                         Configurable concurrent task
                                      execution

  Maintainability                     Modular Python services and typed
                                      interfaces

  Traceability                        Persist all important state changes
                                      and tool calls

  Performance                         Run independent tasks concurrently
                                      where safe

  Cost control                        Enforce token, call, and project
                                      budgets

  Extensibility                       Add tools and agent roles through
                                      explicit configuration

  Portability                         Support documented local
                                      Docker-based execution

  Data integrity                      Use transactions and constraints
                                      for critical state

  Testability                         Unit and integration tests for
                                      orchestration and policy services
  -----------------------------------------------------------------------

## 24. Initial Acceptance Criteria

The MVP is considered functionally complete when all of the following
are demonstrated:

1.  A user can submit a natural-language software requirement.
2.  The Planning Agent produces a schema-valid plan with requirements,
    architecture, tasks, dependencies, and acceptance criteria.
3.  The orchestrator validates and persists the plan.
4.  A human can approve or reject the plan.
5.  The four primary agents can be initialized with separate
    instructions and memory namespaces.
6.  The task manager enforces ownership, dependencies, and valid state
    transitions.
7.  Independent frontend and backend tasks can run concurrently.
8.  Agents communicate only through the persisted Message Bus.
9.  Tool requests pass through the Tool Gateway.
10. Unauthorized file operations are rejected and audited.
11. Agent code executes in restricted Docker containers.
12. Git worktrees prevent concurrent agents from sharing a mutable
    working directory.
13. The Testing Agent can generate and execute tests in its authorized
    workspace.
14. Defects can be converted into bounded repair tasks.
15. Integration requires automated validation and configured approval.
16. A failed workflow can resume from a persisted checkpoint without
    losing completed work.
17. Azure OpenAI usage is tracked and bounded by configured budgets.
18. The platform produces a final report with source references and test
    results.
19. No agent framework or non-Azure model provider is used.
20. Automated tests cover permission enforcement, task transitions,
    dependency scheduling, message validation, and recovery.

## 25. Implementation Roadmap

### Phase 1: Core foundation

-   Python package structure and configuration.
-   Azure OpenAI client.
-   Pydantic schemas.
-   SQLite schema and repository layer.
-   Task manager and state machine.
-   Basic deterministic orchestrator.
-   Structured logging and audit events.

**Exit criteria:** A project can be created, planned output can be
validated and persisted, and tasks can be created and transitioned under
policy.

### Phase 2: Agent runtime and memory

-   Base agent runtime.
-   Four primary agent definitions.
-   Prompt and instruction versioning.
-   Private and shared memory services.
-   Context builder and retrieval.
-   Persisted message bus.
-   Structured output validation.

**Exit criteria:** Agents can receive bounded task context, communicate
through the bus, and persist isolated memory.

### Phase 3: Secure tools and workspaces

-   Tool Gateway.
-   Permission manager.
-   File ownership and locks.
-   Git worktree manager.
-   Docker sandbox manager.
-   Restricted filesystem and command tools.
-   Security audit tests.

**Exit criteria:** An agent can modify only authorized files and execute
approved commands in an isolated container.

### Phase 4: Planning and parallel development

-   Requirement analysis.
-   Plan validation and approval.
-   Dependency-aware scheduler.
-   Frontend and backend implementation workflows.
-   Contract management.
-   Bounded sub-agent creation.

**Exit criteria:** A project can be decomposed and independent
frontend/backend tasks can execute concurrently against approved
contracts.

### Phase 5: QA and integration

-   Test generation and execution.
-   Bug report schema and repair task creation.
-   Integration Manager.
-   Merge validation and approval.
-   Regression and end-to-end testing.

**Exit criteria:** A project can pass through implementation, controlled
integration, QA, and bounded repair cycles.

### Phase 6: Recovery and delivery

-   Checkpointing and recovery.
-   Idempotency controls.
-   Cost and usage budgets.
-   Final reports and artifact packaging.
-   Operational documentation.

**Exit criteria:** An interrupted project can resume and produce a
traceable delivery package.

## 26. Suggested Repository Structure

``` text
ai-dev-team/
├── app/
│   ├── main.py
│   ├── orchestrator/
│   │   ├── engine.py
│   │   ├── scheduler.py
│   │   ├── workflow.py
│   │   ├── dependency_manager.py
│   │   ├── integration_manager.py
│   │   └── recovery_manager.py
│   ├── agents/
│   │   ├── base_agent.py
│   │   ├── planning/
│   │   ├── frontend/
│   │   ├── backend/
│   │   └── testing/
│   ├── runtime/
│   │   ├── agent_runtime.py
│   │   ├── context_builder.py
│   │   └── execution_manager.py
│   ├── ai/
│   │   ├── azure_client.py
│   │   ├── tool_call_parser.py
│   │   ├── response_validator.py
│   │   └── token_tracker.py
│   ├── tools/
│   │   ├── tool_gateway.py
│   │   ├── filesystem.py
│   │   ├── terminal.py
│   │   ├── git_manager.py
│   │   ├── docker_manager.py
│   │   └── test_runner.py
│   ├── memory/
│   │   ├── memory_manager.py
│   │   ├── agent_memory.py
│   │   ├── project_memory.py
│   │   └── retrieval.py
│   ├── tasks/
│   │   ├── task_manager.py
│   │   ├── task_validator.py
│   │   └── state_machine.py
│   ├── communication/
│   │   ├── message_bus.py
│   │   └── message_models.py
│   ├── security/
│   │   ├── permission_manager.py
│   │   ├── file_ownership.py
│   │   ├── sandbox_policy.py
│   │   └── audit_logger.py
│   ├── database/
│   │   ├── models.py
│   │   ├── repository.py
│   │   └── migrations/
│   └── schemas/
│       ├── agent.py
│       ├── task.py
│       ├── message.py
│       └── project.py
├── projects/
├── workspaces/
├── memory/
├── logs/
├── artifacts/
├── tests/
├── config/
├── scripts/
├── .env.example
├── pyproject.toml
└── README.md
```

This structure is a starting point. Keep modules small and introduce
abstractions only where they enforce a real boundary or simplify
testing.

## 27. Open Decisions Before Production

The following decisions must be resolved before a production deployment:

-   Which Azure OpenAI deployments and model capabilities are available?
-   What are the default per-project and per-task token budgets?
-   Which frontend and backend technology stacks are supported
    initially?
-   Is the initial interface CLI-only, API-based, or web-based?
-   Which network destinations, if any, may execution containers access?
-   What approval roles and identity mechanism are required?
-   What are the artifact retention and project deletion policies?
-   Which static security checks are mandatory for every project?
-   What is the required backup and restore procedure for SQLite?
-   When should PostgreSQL replace SQLite?

## 28. Final Architectural Rule

**The LLM proposes. The Python platform decides.**

No agent may independently authorize itself, change authoritative
workflow state, bypass tool permissions, write outside its workspace,
alter another agent's memory, execute unrestricted host commands, or
merge unreviewed code.

This rule is the foundation of AI Dev Team's security, reliability, and
predictable operation.
