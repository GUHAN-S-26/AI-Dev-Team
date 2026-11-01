# Local Dashboard API

The dashboard binds to 127.0.0.1 by default. Start it with ai-dev-team dashboard. Configure the first admin explicitly with AI_DEV_TEAM_ADMIN_USERNAME and AI_DEV_TEAM_ADMIN_PASSWORD; credentials are never returned by the API.

## Authentication

POST /api/auth/login accepts {username,password} and returns a user record plus a CSRF token. The session is an HttpOnly cookie. Send X-CSRF-Token on state-changing requests.

GET /api/auth/session validates the cookie and rotates the CSRF token. POST /api/auth/logout expires the cookie.

## Read APIs

- GET /api/health — unauthenticated liveness response.
- GET /api/projects — authenticated project summaries, pending approvals, and aggregate token usage.
- GET /api/projects/{project_id} — project, tasks, agents, activity, and artifact metadata.
- GET /api/projects/{project_id}/metrics — derived task/execution/tool/token/artifact metrics.

## Write APIs

- POST /api/projects — developer/admin; creates a validated project.
- POST /api/approvals/{approval_id}/decision — reviewer/admin; approves or rejects with a bounded reason.

All JSON bodies are bounded to 64 KiB. Errors are generic for unexpected server failures. The API never exposes Azure keys or raw session tokens in JSON.

