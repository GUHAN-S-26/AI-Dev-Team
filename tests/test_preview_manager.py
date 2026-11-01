from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.database.repository import Repository
from app.schemas.models import Project
from app.web.preview import PreviewError, PreviewManager


def test_preview_command_is_argv_only_and_allowlisted() -> None:
    assert PreviewManager.validate_command(["python", "backend/server.py"]) == ["python", "backend/server.py"]
    with pytest.raises(PreviewError):
        PreviewManager.validate_command(["sh", "-c", "unsafe"])
    with pytest.raises(PreviewError):
        PreviewManager.validate_command(["python\x00", "server.py"])


def test_preview_start_uses_project_workspace_and_loopback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects", workspaces_dir=tmp_path / "workspaces")
    settings.ensure_directories()
    root = settings.projects_dir / "PROJECT-preview"
    root.mkdir(parents=True)
    repository = Repository(settings.database_path)
    project = Project(project_id="PROJECT-preview", name="Preview", requirement="Build preview", root_path=str(root))
    repository.create_project(project)
    manager = PreviewManager(settings, repository)
    captured: list[list[str]] = []

    def fake_docker(args: list[str], timeout: int = 30):
        captured.append(args)
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(manager, "_docker", fake_docker)
    monkeypatch.setattr(manager, "_ready", lambda port: True)
    session = manager.start(project.project_id)
    assert session.status == "RUNNING"
    assert session.url is not None and session.url.startswith("http://127.0.0.1:")
    assert any(item == "--publish" for item in captured[0])
    assert any(value.startswith("127.0.0.1:") for value in captured[0])
