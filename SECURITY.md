# Security Model

## Trust boundaries

Model responses, repository content, generated code, test output, browser output, and artifact text are untrusted data. They cannot change authorization rules or workflow state.

Azure credentials remain in the trusted host process. They are not placed in browser HTML, project memory, Docker environment variables, prompts, or logs.

## Authentication and authorization

Dashboard sessions use scrypt password hashes, random bearer tokens stored only as SHA-256 hashes, expiry timestamps, HttpOnly/SameSite cookies, CSRF hashes, login throttling, request rate limiting, and role permissions:

- viewer: read-only telemetry and artifacts
- developer: viewer plus project creation and operational actions
- reviewer: viewer plus approval decisions
- admin: all dashboard permissions

All state-changing dashboard requests require a CSRF header. Approval and merge decisions remain separate from model output.

## File and tool controls

Every agent file operation is checked for canonical path containment, symlink/path traversal, agent/task ownership, tool allowlists, and locks. Commit paths are checked by the same Permission Manager before staging. Agents cannot merge directly to main.

## Execution isolation

Docker runs as UID 65532 with dropped capabilities, no-new-privileges, a read-only root filesystem, bounded CPU/memory/PIDs, a writable workspace/tmpfs only, and network disabled by default. Playwright must run in the configured isolated browser image.

## Data protection

Audit records omit credentials and full sensitive prompts. Dashboard payloads contain derived project state only. SQLite restore requires explicit confirmation. Destructive, network, secret, merge, and release operations remain approval-gated by policy.

