from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.database.repository import Repository
from app.orchestrator.engine import Orchestrator


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        projects_dir=tmp_path / "projects",
        workspaces_dir=tmp_path / "workspaces",
    )


@pytest.fixture
def repository(settings: Settings) -> Repository:
    settings.ensure_directories()
    return Repository(settings.database_path)


@pytest.fixture
def orchestrator(settings: Settings, repository: Repository) -> Orchestrator:
    return Orchestrator(settings, repository)
