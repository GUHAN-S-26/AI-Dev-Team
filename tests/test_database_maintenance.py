from __future__ import annotations

from pathlib import Path

import pytest

from app.database.repository import Repository
from app.schemas.models import Project, ProjectStatus, new_id


def test_sqlite_backup_restore_and_explicit_restore_gate(tmp_path: Path) -> None:
    source = Repository(tmp_path / "source.sqlite3")
    project = Project(project_id=new_id("PROJECT"), name="Backup", requirement="Build a backup test", root_path=str(tmp_path))
    source.create_project(project)
    backup = source.backup_to(tmp_path / "backup.sqlite3")
    assert backup.is_file()
    assert source.schema_version() == 2
    restored = Repository(tmp_path / "restored.sqlite3")
    with pytest.raises(PermissionError):
        restored.restore_from(backup)
    restored.restore_from(backup, confirm=True)
    loaded = restored.get_project(project.project_id)
    assert loaded is not None
    assert loaded.status is ProjectStatus.CREATED
