"""Persistence ports kept independent from the SQLite implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.schemas.models import Project, Task


class ProjectRepositoryPort(Protocol):
    """Minimum repository contract consumed by dashboard and orchestration services."""

    def get_project(self, project_id: str) -> Project | None: ...

    def list_projects(self) -> list[Project]: ...

    def list_tasks(self, project_id: str) -> list[Task]: ...

    def backup_to(self, target: Path) -> Path: ...

    def schema_version(self) -> int: ...
