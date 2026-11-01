"""Validated application configuration.

Configuration is deliberately host-side. It is never copied into agent
prompts or execution containers.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class Settings(BaseModel):
    data_dir: Path = Field(default=Path("./data"))
    projects_dir: Path = Field(default=Path("./projects"))
    workspaces_dir: Path = Field(default=Path("./workspaces"))
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_deployment: str | None = None
    request_timeout_seconds: float = Field(default=90.0, gt=0, le=600)
    max_concurrency: int = Field(default=4, ge=1, le=32)
    max_retries: int = Field(default=3, ge=0, le=10)
    max_project_tokens: int = Field(default=200_000, ge=1_000)
    max_task_tokens: int = Field(default=30_000, ge=100)
    max_output_chars: int = Field(default=20_000, ge=1_000)
    docker_image: str = "python:3.12-slim"
    docker_timeout_seconds: int = Field(default=300, ge=1, le=3600)
    require_merge_approval: bool = True
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = Field(default=8080, ge=1, le=65535)
    dashboard_admin_username: str | None = None
    dashboard_admin_password: str | None = None
    session_ttl_seconds: int = Field(default=3600, ge=300, le=86_400)
    secure_cookie: bool = False
    playwright_image: str = "ai-dev-team-playwright:1.55.0"
    playwright_timeout_seconds: int = Field(default=120, ge=10, le=900)

    @field_validator("azure_openai_endpoint")
    @classmethod
    def validate_endpoint(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("https://"):
            raise ValueError("Azure OpenAI endpoint must use HTTPS")
        return value

    @classmethod
    def from_env(cls, env_file: Path | None = Path(".env")) -> Settings:
        cls._load_env_file(env_file)

        def optional(name: str) -> str | None:
            value = os.environ.get(name)
            return value if value else None

        return cls(
            data_dir=Path(os.environ.get("AI_DEV_TEAM_DATA_DIR", "./data")),
            projects_dir=Path(os.environ.get("AI_DEV_TEAM_PROJECTS_DIR", "./projects")),
            workspaces_dir=Path(os.environ.get("AI_DEV_TEAM_WORKSPACES_DIR", "./workspaces")),
            azure_openai_endpoint=optional("AZURE_OPENAI_ENDPOINT"),
            azure_openai_api_key=optional("AZURE_OPENAI_API_KEY"),
            azure_openai_api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            azure_openai_deployment=optional("AZURE_OPENAI_DEPLOYMENT"),
            max_concurrency=int(os.environ.get("AI_DEV_TEAM_MAX_CONCURRENCY", "4")),
            max_retries=int(os.environ.get("AI_DEV_TEAM_MAX_RETRIES", "3")),
            max_project_tokens=int(os.environ.get("AI_DEV_TEAM_MAX_PROJECT_TOKENS", "200000")),
            max_task_tokens=int(os.environ.get("AI_DEV_TEAM_MAX_TASK_TOKENS", "30000")),
            max_output_chars=int(os.environ.get("AI_DEV_TEAM_MAX_OUTPUT_CHARS", "20000")),
            docker_image=os.environ.get("AI_DEV_TEAM_DOCKER_IMAGE", "python:3.12-slim"),
            docker_timeout_seconds=int(os.environ.get("AI_DEV_TEAM_DOCKER_TIMEOUT_SECONDS", "300")),
            require_merge_approval=os.environ.get("AI_DEV_TEAM_REQUIRE_MERGE_APPROVAL", "true").lower()
            in {"1", "true", "yes", "on"},
            dashboard_host=os.environ.get("AI_DEV_TEAM_DASHBOARD_HOST", "127.0.0.1"),
            dashboard_port=int(os.environ.get("AI_DEV_TEAM_DASHBOARD_PORT", "8080")),
            dashboard_admin_username=optional("AI_DEV_TEAM_ADMIN_USERNAME"),
            dashboard_admin_password=optional("AI_DEV_TEAM_ADMIN_PASSWORD"),
            session_ttl_seconds=int(os.environ.get("AI_DEV_TEAM_SESSION_TTL_SECONDS", "3600")),
            secure_cookie=os.environ.get("AI_DEV_TEAM_SECURE_COOKIE", "false").lower() in {"1", "true", "yes", "on"},
            playwright_image=os.environ.get("AI_DEV_TEAM_PLAYWRIGHT_IMAGE", "ai-dev-team-playwright:1.55.0"),
            playwright_timeout_seconds=int(os.environ.get("AI_DEV_TEAM_PLAYWRIGHT_TIMEOUT_SECONDS", "120")),
        )

    @staticmethod
    def _load_env_file(env_file: Path | None) -> None:
        """Load simple KEY=value settings without shell evaluation or logging.

        Existing process environment variables always win. Values are kept only
        in the process environment and are never returned in diagnostics.
        """
        if env_file is None or not env_file.is_file():
            return
        key_pattern = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            if "=" not in line:
                continue
            key, value = (part.strip() for part in line.split("=", 1))
            if not key_pattern.fullmatch(key):
                continue
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            os.environ.setdefault(key, value)

    @property
    def database_path(self) -> Path:
        return self.data_dir / "ai_dev_team.sqlite3"

    def ensure_directories(self) -> None:
        for path in (self.data_dir, self.projects_dir, self.workspaces_dir):
            path.mkdir(parents=True, exist_ok=True)
