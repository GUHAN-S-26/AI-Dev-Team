# AI Dev Team Implementation Status

## Current phase and task

Phase 3 multi-project AI development workspace — completed and verified as a chat-first IDE with project-scoped conversations, workflow controls, secure live previews, and responsive application-centered UI. Phase 2 remains verified: dashboard/API, SQLite reliability, observability, documentation, Azure integration, Docker sandboxing, isolated Playwright evidence, frontend behavior, integration, QA, delivery, and final quality/security checks all passed.

## Currently implementing

Phase 3 implementation is complete. The existing orchestrator, agents, Azure boundary, SQLite repository, authentication, RBAC, CSRF, audit, worktrees, Docker sandbox, and QA evidence were preserved.

Phase 3 implementation plan:

1. Add schema migration for project memberships, project-scoped chat, and persisted preview sessions; add repository isolation tests.
2. Add a deterministic workspace service that persists chat, invokes the existing orchestrator, schedules approved workflow stages, and records assistant/activity events.
3. Add a Docker-backed loopback-only preview manager with lifecycle/error handling and a browser-isolated preview iframe.
4. Replace the monitoring-focused dashboard UI with a responsive three-panel, chat-first multi-project workspace and real preview/artifact tabs.
5. Add API, auth/isolation, workflow, preview, and Playwright acceptance coverage; run all quality/security checks and update this file after every milestone.

Lifecycle checkpoint before live acceptance: the first two isolated dashboard
browser runs reached the sandbox timeout without a usable report. Investigation
identified that the dashboard's bounded workflow executor was not closed during
signal-driven shutdown, so the browser worker could not finish its cleanup.
The shutdown path now closes the `WorkspaceService` executor after the HTTP
server exits. Focused Ruff and strict mypy checks passed for this fix, and the
live acceptance run subsequently passed.

The repeated single-viewport smoke run then exposed a separate environment
blocker: the pinned Playwright image lacked the dashboard's runtime packages,
and its child process failed before readiness with
`ModuleNotFoundError: No module named 'pydantic'`. The image definition is being
updated to include the existing application's runtime dependencies; sandbox
restrictions remain unchanged.

That image update is complete (`pydantic==2.13.5`, `openai==2.54.0`, and
`Pillow==11.3.0`), and the browser worker now waits for asynchronous text
assertions while preserving real diagnostics. The correctly mounted, isolated
dashboard acceptance run passed across all three responsive viewports. A real
preview run then exposed and fixed the container-interface bind issue; the
generated application now starts in its restricted container and responds to
`/health` through a host-loopback-only published port. Full post-fix
quality/security checks also passed.

Phase 2 completed baseline:

1. Create the `v1.0.0-mvp` Git checkpoint in the clean verified project repository and preserve the SQLite/artifact state.
2. Add production observability and repository services: migrations, backup/restore, dashboard read models, structured monitoring, graceful shutdown, and recovery reconciliation.
3. Add dashboard/API with secure sessions, authentication, RBAC, authorization, rate limiting, approval controls, and no frontend secret exposure.
4. Add the isolated Playwright subsystem: readiness, browser workflows, responsive screenshots, console/network/browser diagnostics, traces, HTML reports, artifacts, and visual diffs. **Completed with live baseline and repeat-run evidence.**
5. Investigate all seven skipped live-project tests; add security, API, concurrency, permission-bypass, Docker isolation, recovery, Playwright, and visual-regression coverage. **Completed: all seven tests passed inside the validated browser image.**
6. Write and maintain `ARCHITECTURE.md`, `SECURITY.md`, `API_DOCUMENTATION.md`, `DEPLOYMENT.md`, and `QA_DOCUMENTATION.md`, then run the full quality/security suite.

Every milestone must have executable tests and recorded evidence before it is marked complete.

## Completed functionality

- Phase 3 schema migration implemented: project memberships, project-scoped chat messages, and persisted preview sessions are created transactionally at schema version 2 without changing existing project/task tables.
- Phase 3 workspace backend implemented: authenticated project membership filtering, project chat persistence, bounded background workflow jobs, plan/integration approval handoffs, QA/browser-QA/delivery progression, and project workspace read models are available through the existing dashboard server.
- Phase 3 preview runtime implemented: per-project Docker container lifecycle, read-only project mounts, non-root/resource restrictions, loopback-only published ports, readiness checks, persisted errors/status, and no browser access to dashboard cookies or secrets.
- Phase 3 workspace UI implemented: responsive project sidebar/search, project-specific chat, approval cards, live application iframe, final/QA/screenshot/activity/artifact tabs, refresh/open controls, and authenticated login/logout.
- Phase 3 runtime hardening implemented: dashboard executor shutdown closes cleanly, the pinned Playwright image includes the dashboard runtime dependencies, browser text assertions wait for asynchronous UI updates, and the controlled preview default binds the generated app to the container interface while retaining host-loopback-only exposure.

- PRD.md read completely (1463 lines).
- Repository inventory completed; repository contained only PRD.md.
- Implementation plan recorded.
- Typed domain schemas and validated environment configuration created.
- Transactional SQLite repository created with projects, agents, memory, tasks, executions, messages, approvals, ownership, locks, tool calls, audit, checkpoints, artifacts, and model usage tables.
- Task state machine, dependency-cycle validation, and deterministic async scheduler created.
- Azure OpenAI-only client boundary and structured response validation created.
- Private/shared memory services and persisted idempotent message bus created.
- Python-enforced path ownership, symlink/path traversal checks, locks, typed Tool Gateway, Docker sandbox policy, and Git worktree manager created.
- Azure function-tool execution loop added with bounded rounds, untrusted tool-result feedback, required committed work, and deterministic recovery finalization limited to authorized changed paths.
- Existing-agent authorization migration now includes owned directory roots as well as descendants; commit paths are checked by the Permission Manager before staging.
- Pinned Docker sandbox image created at `docker/sandbox.Dockerfile` with pytest 8.3.3 and non-root UID 65532.
- Live project `PROJECT-197fdb8c2e7d` completed Planning, Frontend, Backend, Testing, human-approved Integration, and final QA.
- Delivery artifact generated at `data/artifacts/PROJECT-197fdb8c2e7d/final-report.json`; integrated project worktree is clean on `main`.
- Phase 2 foundation completed: schema version tracking, users/sessions tables, scrypt password hashing, hashed bearer sessions, CSRF hashes, RBAC permissions, login/request rate limiting, project/audit/tool/usage read models, and session expiration cleanup.
- Dashboard/API foundation completed: self-contained responsive dashboard, project listing/creation, agent/task/activity/artifact views, health endpoint, login/logout/session APIs, CSRF-protected project writes, RBAC-protected approval decisions, security headers, bounded JSON bodies, and graceful SIGTERM/SIGINT shutdown.
- SQLite reliability foundation completed: schema version reporting, consistent backup, explicit-confirmation restore, and a repository protocol suitable for a future PostgreSQL adapter.
- Monitoring foundation completed: derived task/execution/tool/token/artifact metrics and dashboard metrics endpoint, with no prompt or credential exposure.
- Playwright subsystem completed: argv-only app startup, loopback readiness, responsive viewport capture, component screenshots, diagnostics, traces/videos, HTML/JSON reports, explicit baselines, and Pillow pixel diffs with no automatic visual acceptance.
- Playwright production image completed: pinned Microsoft browser base plus `playwright==1.55.0`, non-root validation, and a task-scoped cleanup path for container-owned temporary files.
- Live Playwright evidence completed: baseline run produced desktop/tablet/mobile screenshots, traces, and videos; repeat run passed with zero changed pixels at all three viewports and no console, request, browser, or image errors.
- Required operational documents completed: `ARCHITECTURE.md`, `SECURITY.md`, `API_DOCUMENTATION.md`, `DEPLOYMENT.md`, and `QA_DOCUMENTATION.md`.

## Files created or modified

- `pyproject.toml`, `.env.example`, `.bandit`, `README.md`
- `app/config.py`, `app/main.py`
- `app/schemas/*`, `app/database/*`
- `app/tasks/*`, `app/orchestrator/*`
- `app/agents/*`, `app/runtime/*`, `app/ai/*`
- `app/memory/*`, `app/communication/*`, `app/security/*`
- `app/tools/*`, `app/qa/*`
- `app/web/*`, `app/observability/*`, `ARCHITECTURE.md`, `SECURITY.md`, `API_DOCUMENTATION.md`, `DEPLOYMENT.md`, `QA_DOCUMENTATION.md`
- `tests/*`
- Phase 3 additions/fixes: `app/web/workspace.py`, `app/web/preview.py`, `app/web/dashboard.py`, `app/qa/browser_worker.py`, `docker/playwright.Dockerfile`, repository/schema migration changes, and multi-project workspace tests.

## Tests executed and results

- Initial schema-migration regression: 18 passed, 1 failed because the pre-Phase-3 maintenance test expected schema version 1; the test was updated for schema version 2 and the regression is resolved.
- Schema/workspace persistence/API checkpoint: compilation, Ruff, strict mypy, and pytest (`23 passed`) passed; focused membership, chat, preview command, and dashboard isolation tests passed.

- Syntax/import checkpoint: `python3 -m compileall -q app` passed.
- `pytest -q`: 10 passed.
- `ruff check app tests`: passed.
- `mypy app`: passed with strict mode.
- `bandit -c .bandit -q -r app`: passed. The configuration explicitly documents the controlled subprocess calls used for Git/Docker and the Docker tmpfs path.
- CLI smoke test: `app.main create` passed and created a Git-backed project with four agents and a persisted checkpoint.
- End-to-end control-plane test with a deterministic Azure-boundary test double: plan generation, human approval, task persistence, concurrent worktree scheduling, execution records, and completion all passed.
- Integration/delivery test: unapproved merges were rejected; approved Git worktrees merged; QA evidence was persisted; final delivery report was generated and project completion was recorded.
- Final verification command passed: Ruff, strict mypy, pytest (10 passed), Bandit with the documented control-plane config, and Python bytecode compilation.
- Configuration regression test passed; test suite now reports 11 passed.
- Azure client compatibility changes are statically validated but not yet authenticated against the configured deployment.
- Authenticated attempt result: endpoint/key/deployment presence verified without disclosure; deployment name matched GPT-6.1 Sol; request reached Azure and returned HTTP 400 because `temperature=0` is unsupported.
- Second authenticated attempt result: request reached Azure and returned HTTP 400 for missing strict-schema `additionalProperties=false`; no credentials were exposed.
- Third authenticated attempt result: structured response succeeded; Pydantic validation passed, response `ok=true`, 80 prompt tokens, 19 completion tokens, approximately 2.6 seconds latency.
- Tool-calling attempt result: Azure returned HTTP 400 stating function tools with reasoning enabled require `/v1/responses` or `reasoning_effort='none'`; no tool was executed.
- Responses tool-calling attempt result: configured API version returned HTTP 404 Resource not found; `.env` was not modified.
- Alternate-version result: `2025-04-01-preview` returned one parsed `record_validation` proposal with 61 prompt tokens and 18 completion tokens.
- Final `.env`-path result: structured output passed with 99 total tokens; Responses tool calling passed with one parsed proposal and 79 total tokens.
- Docker result: daemon reachable; configured image was initially absent, then pulled; restricted sandbox command passed as non-root UID 65532.
- Pre-live workflow audit found two bugs: CLI plan approval did not materialize tasks, and final QA targeted the testing worktree instead of integrated main.
- Live planning attempt found a third bug: strict schema normalization did not close open-ended dictionary object nodes in the plan schema.
- Planning retry found a fourth schema edge case: empty object nodes also require explicit `properties` and `required` arrays for Azure strict outputs.
- The next planning retry found a fifth schema edge case: Azure rejects `default` beside `$ref` nodes; boundary normalization now removes schema defaults because strict output requires every field explicitly.
- The next planning response was schema-valid JSON but proposed an unauthorized `integration` task owner; Pydantic correctly rejected it. Planning instructions now explicitly restrict task owners to the four primary agents and identify integration/QA/delivery as orchestrator stages.
- Planning retry result: succeeded with 5 tasks and assigned roles `backend`, `frontend`, `planning`, and `testing`.
- Live development result before fix: plan approval persisted, worktrees were created, but the planning-owned task failed with `agent did not report completed work`; frontend/backend/testing remained pending. No downstream success is claimed.
- Recovery result after the planning-task fix: the planning task completed, but the frontend agent still returned `completed=false` without tool-backed file changes; backend was left in progress by the concurrent scheduler. This is a real execution failure, not an E2E success.
- Live execution fixes verified: empty-worktree tool feedback, bounded multi-round proposals, authorized recovery commit finalization, unique usage IDs, and explicit Git merge identity.
- Live development final result: all 5 planned tasks completed, with committed changes in frontend, backend, and testing worktrees.
- Live integration final result: human approval was required and present; 3 merge commits were created and project status became `QA`.
- Live final QA result: Docker sandbox report `PASS`, 7 passed, 0 failed, 7 skipped. Pytest emitted only read-only cache warnings; no test failed.
- Delivery result: final report file exists and project status is `COMPLETED`.
- Final quality/security result: `python3 -m compileall -q app`, `ruff check app tests`, `mypy app`, `pytest -q` (11 passed), and `bandit -c .bandit -q -r app` all exited successfully. Integrated project `git diff --check` also passed.
- Phase 2 foundation verification: Ruff, strict mypy, and pytest (11 passed) passed after the auth and repository changes.
- Dashboard/reliability verification: Ruff, strict mypy, and pytest (13 passed) passed.
- Monitoring verification: Ruff, strict mypy, and pytest (14 passed) passed.
- Playwright/security verification: Ruff, strict mypy, pytest (19 passed), and Bandit passed; baseline creation, second-run visual comparison, loopback readiness validation, artifact layout, and browser-worker security checks are covered.
- Live browser packaging verification: official image lacked the Python binding; the pinned derived image built successfully, imported Playwright as UID 65532 with read-only root, network disabled, and the restricted sandbox flags; live baseline and repeat visual PASS were verified.
- Skipped-test reclassification completed: all seven previously skipped `tests/test_frontend_validation.py` tests passed inside the restricted Playwright container (`7 passed in 1.06s`) with the integrated application running on loopback. No browser tests remain skipped for this validated project run.
- Phase 3 dashboard acceptance completed: the correctly mounted Playwright container executed 66 authenticated workflow actions across desktop, tablet, and mobile; 66 passed, 0 failed, with no console errors, failed requests, or browser errors. Desktop/tablet/mobile screenshots, traces, and videos were produced and all three visual baselines were created for the isolated run.
- Phase 3 preview acceptance completed: the actual generated project ran in `ai-dev-team-sandbox:2026-10-31` as non-root with the read-only workspace mount and responded `200` to `/health` through a `127.0.0.1` published port; the container was stopped and persisted preview state became `STOPPED`.
- Final Phase 3 quality/security checkpoint: `python3 -m compileall -q app` passed; `ruff check app tests` passed; `mypy app` passed with no issues in 55 source files; `pytest -q` passed 23 tests; and `bandit -c .bandit -q -r app` passed with no findings.
- Dashboard launch checkpoint: the real project-backed dashboard is running on `127.0.0.1:8080` and `/api/health` returned `{"status":"ok"}`. `.env` was not modified; because it contained no dashboard admin bootstrap values and the database had no users, a process-only local admin bootstrap was supplied for this running instance.
- Documentation milestone: `README.md` now documents the multi-project chat-first workspace, dashboard startup and admin bootstrap, approval-driven workflow, real Docker preview, project isolation, security boundaries, CLI compatibility, and the verified Phase 3 checks. `ruff check app tests` and `python3 -m compileall -q app` passed after the documentation update.
- Documentation clarification milestone: `README.md` now explains the end-to-end project workflow, identifies the four primary agents and the Orchestrator/sub-agent model, and provides a brief repository and generated-project file-structure guide. No application code or security behavior changed.
- Live dashboard workflow milestone: project `PROJECT-d3ec493ee88d` (`Neighborhood Cafe Website`) was created through the authenticated web UI, received a natural-language build request, produced a validated plan, passed human plan approval and integration approval, and reached `COMPLETED` with 5/5 tasks at 100%. Persisted task execution records show Planning, Frontend, Backend, and Testing completed; the dashboard Agent Activity view now derives truthful statuses, current-task details, execution/tool records, and percentages from task state instead of stale agent-creation records.
- Live preview defect correction milestone: the generated project initially returned HTTP 404 at `/` because the Frontend Agent wrote `frontend/index.html` while the Backend server only served `public/`. The generated server now securely serves `public/` first and falls back to `frontend/` without relaxing traversal or private-file protections; the corrected project change was committed as `5bbe0a9`.
- Preview/QA hardening milestone: preview readiness and browser navigation now require HTTP 200, failed navigation/workflow/console/request/browser/image diagnostics produce QA `FAIL`, and Playwright workspace paths are normalized before creating the isolated worker directory. The dashboard iframe was refreshed and its accessibility tree exposed the actual generated Juniper & Grain cafe application, including the heading, menu cards, opening-hours table, and health-backed runtime.
- Final live application verification: the repaired project returned HTTP 200 for `/`, `{"status":"ok"}` for `/api/health`, and 404 for traversal/private-file probes. The additional isolated content-aware Playwright run passed desktop, tablet, and mobile assertions for `main`, the generated heading, `House espresso`, and `Monday`; it produced 3 screenshots, 9 component screenshots, and 3 traces, with no console errors, failed requests, browser errors, broken images, workflow failures, or visual changes (`0.0` changed-pixel ratio on all viewports). Stale baselines from the earlier invalid 404 run were preserved under `data/artifacts/PROJECT-d3ec493ee88d/stale-baselines-from-invalid-preview/` and were not used for the final PASS.
- Post-fix quality checkpoint: `python3 -m compileall -q app`, `ruff check app tests`, strict `mypy app` (55 source files), `pytest -q` (23 passed), and `bandit -c .bandit -q -r app` all passed after the preview and QA fixes.
- Final dashboard reload checkpoint: the updated dashboard process restarted cleanly on `127.0.0.1:8080`; the selected project still showed `COMPLETED`, `5/5 tasks · 100%`, the actual Juniper & Grain application rendered inside Live Preview, and Agent Activity showed backend, frontend, planning, and testing as `Completed` with 100% task progress and persisted execution details.
- Responsive UI milestone: the authenticated workspace shell was visually upgraded with responsive grid/drawer breakpoints, improved panel hierarchy, touch-sized controls, focus-visible states, mobile-safe `dvh` sizing, scrollable project/output navigation, stronger status cards, and an explicit mobile/tablet preview Close control. The pinned Playwright container validated 1440, 1180, 1024, 768, 390, and 320 pixel viewports with no horizontal overflow; preview geometry and open/close behavior passed at every responsive breakpoint.
- Chat/approval UX milestone: the chat scroller now uses a flex-safe `min-height: 0`, immediate programmatic anchoring, and bottom-anchor preservation across viewport resize while respecting manual user scrolling. Primary controls are standardized to 40px visible height, and status pills use consistent alignment. Planning messages now render the persisted Planning Agent output as an accessible implementation-plan card with the brief, architecture summary, requirements, assigned tasks, descriptions, and acceptance criteria before the approval card. Live browser validation confirmed bottom gaps of `0` at all six tested viewports, visible plan tasks, consistent button heights, and successful approval-drawer controls.
- Final live sandbox rerun completed after the ownership hardening: actual `DockerSandbox` execution returned `PASS`, all three visual diffs remained at `0.0`, diagnostics remained empty, and no temporary `playwright-*` directories remained after cleanup.
- Final Phase 2 checkpoint: `python3 -m compileall -q app`, Ruff, strict mypy, pytest (`19 passed in 1.04s`), Bandit, all five required document-presence checks, and integrated-project `git diff --check` passed. The root volume has approximately 30 GB available; no unrelated user data was deleted.

## Errors or blockers

- No current implementation blockers. Historical environment notes: `rg` is unavailable, so `find` was used for inspection; live Azure operation requires the configured endpoint/key/deployment; and generated-code execution remains Docker-only with network disabled by default. Phase 3 dashboard, preview, and post-fix quality/security checks are verified. The Playwright workflow used isolated test credentials and no provider secrets. The live dashboard run verified the persisted four-agent workflow and generated application; the final content-aware browser pass verified the repaired runtime independently.
- Live Playwright storage, packaging, path-mapping, and container-owned cleanup issues were resolved and verified. Temporary output is removed with a confined symlink-safe cleanup routine.

## Pending tasks

- Optional production hardening remains outside this completed MVP scope: backup/restore policy, PostgreSQL migration, a supported preview-stack catalog, and a dedicated live-Azure browser approval run using controlled credentials.

## Exact next step

Next step: implement and validate scoped project deletion for the existing `Car landing page` project, including confirmation UI, backend/database/storage cleanup, and preservation checks for the other projects.

## Project deletion milestone — complete

- Current phase/task: Multi-project workspace lifecycle; project deletion implemented and verified.
- Currently implementing: no remaining work for this milestone.
- Completed functionality: permission-checked, CSRF-protected DELETE API; running-workflow rejection; preview shutdown; confined project/worktree/artifact directory cleanup; transactional deletion of project-scoped SQLite records; confirmation modal; immediate project-list refresh; success/failure notices. The authorized live target `PROJECT-3a16ceb304fd` (`Car landing page`) was deleted through the dashboard. The other persisted projects remain `PROJECT-d3ec493ee88d` (`Neighborhood Cafe Website`) and `PROJECT-197fdb8c2e7d` (`Live Validation Health App`).
- Files created or modified: `app/database/repository.py`, `app/security/auth.py`, `app/web/workspace.py`, `app/web/dashboard.py`, `tests/test_project_deletion.py`, and this status file.
- Tests executed and results: focused deletion/dashboard checks passed (`4 passed`); full compileall passed; Ruff passed; strict mypy passed for 55 source files; full pytest passed (`25 passed`); and Bandit passed after replacing dynamic SQL interpolation with fixed statements. The live browser confirmation popup, success notice, immediate list removal, and post-refresh absence were verified. Direct storage/database verification found no target DB row and no target project, worktree, or artifact directory; both survivor project roots remained present.
- Final runtime checkpoint: the dashboard was restarted with the final source, `/api/health` returned HTTP 200, and no project-scoped data rows remained for the deleted target except the intentional immutable `PROJECT_DELETED` audit event retained for security traceability.
- Errors or blockers: none currently.
- Pending tasks: none for this requested deletion workflow.
- Exact next step: continue using the running dashboard; future deletions remain scoped to the selected project and require confirmation, authorization, and CSRF validation.

## Temporary Cloudflare Tunnel milestone — complete

- Current phase/task: temporary external access to the authenticated dashboard.
- Completed functionality: restarted the dashboard with secure cookies enabled, started an account-less Cloudflare Quick Tunnel in a host-networked Docker container, and kept the local application bound to `127.0.0.1:8080`.
- Runtime result: local `/api/health` returned HTTP 200; the public tunnel returned HTTP 200 and served the dashboard login page with `Cache-Control: no-store`, `X-Frame-Options: DENY`, and the existing content security policy. The public dashboard was opened and visibly verified at the generated HTTPS URL.
- Security/limitations: this is a temporary, account-less `trycloudflare.com` URL with no uptime guarantee. The tunnel process must remain running; stopping it immediately revokes access. No API keys or secrets were logged or transmitted.
- Pending tasks: none for the requested temporary tunnel.
- Exact next step: use the public HTTPS URL while the tunnel process is running; for durable production access, create a named Cloudflare Tunnel with an authenticated Cloudflare account and a persistent host.

## Public preview recovery milestone — complete

- Current phase/task: Cloudflare Quick Tunnel dashboard validation and project preview recovery.
- Completed functionality: added a project-scoped same-origin preview proxy at `/api/projects/{project_id}/preview/`, rewrote root-relative HTML asset paths into the proxy scope, added a dashboard `Start preview` control, and updated the dashboard CSP to allow only same-origin preview frames plus the existing loopback allowance.
- Security behavior: the proxy requires authenticated project access, forwards only the selected project’s persisted running preview port, keeps Docker ports loopback-only, enforces a 12 MiB response limit, rejects traversal/backslash/NUL path segments, strips internal port/container details from browser workspace data, and returns `SAMEORIGIN`/`frame-ancestors 'self'` protections.
- Runtime result: the `Neighborhood Cafe Website` preview was restarted through the existing Docker `PreviewManager` and reached `RUNNING`; the public Cloudflare dashboard displayed the actual generated cafe application inside the preview iframe. The public DOM contained the generated heading `Your everyday, made a little warmer.` and was no longer blocked.
- Files created or modified: `app/web/dashboard.py`, `tests/test_preview_proxy.py`, and this status file.
- Tests executed and results: focused preview/dashboard tests passed (`5 passed`); full pytest passed (`26 passed`); compileall, Ruff, strict mypy, and Bandit all passed. Public HTTPS returned HTTP 200 and the public preview iframe rendered successfully.
- Errors or blockers: the temporary account-less Quick Tunnel remains non-durable and disappears when its tunnel process stops. The public URL is otherwise verified for the current running process.
- Pending tasks: none for this temporary-tunnel preview fix.
- Exact next step: keep the dashboard and `cloudflared` processes running while using the public URL; use a named Cloudflare Tunnel and persistent host for durable deployment.
