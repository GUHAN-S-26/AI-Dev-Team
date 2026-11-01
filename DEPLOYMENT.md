# Local Deployment

## Requirements

Python 3.12+, Docker, Git, and an Azure OpenAI deployment compatible with structured JSON Schema outputs and Responses API function tools.

Install:

    python3 -m venv .venv
    . .venv/bin/activate
    pip install -e '.[dev]'

Set Azure settings in .env without committing it. Set dashboard credentials explicitly when starting the dashboard:

    export AI_DEV_TEAM_ADMIN_USERNAME=admin
    export AI_DEV_TEAM_ADMIN_PASSWORD='use-a-long-local-password'
    ai-dev-team dashboard

The dashboard listens on loopback by default. Use HTTPS termination and AI_DEV_TEAM_SECURE_COOKIE=true only when an approved local proxy provides TLS. Public deployment is not supported by this MVP upgrade.

## Operations

Use ai-dev-team recover PROJECT-ID after interruption. Create SQLite backups with the repository backup service and test restores in a separate database before any destructive restore. Docker execution refuses host-shell fallback and unapproved network access.

The Playwright image is configured separately from the code-execution image. It must be pinned, available to Docker, and contain the matching Playwright Python package and browser binaries.
Build the pinned Playwright worker image before browser QA:

```text
docker build -f docker/playwright.Dockerfile -t ai-dev-team-playwright:1.55.0 .
```

The image is derived from the pinned Microsoft Playwright browser image and
adds only the matching Python Playwright binding and pinned pytest runner. The worker still runs as
UID 65532, with no network, dropped capabilities, a read-only root
filesystem, bounded resources, and only the project workspace mounted.
