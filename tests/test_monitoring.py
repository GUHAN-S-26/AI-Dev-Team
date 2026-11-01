from __future__ import annotations

from pathlib import Path

from app.database.repository import Repository
from app.observability.monitor import MonitoringService
from app.schemas.models import Project, new_id


def test_monitoring_snapshot_is_derived_and_bounded(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "state.sqlite3")
    project = Project(project_id=new_id("PROJECT"), name="Metrics", requirement="Build metrics", root_path=str(tmp_path))
    repository.create_project(project)
    snapshot = MonitoringService(repository).snapshot(project.project_id)
    assert snapshot.project_id == project.project_id
    assert snapshot.execution_count == 0
    assert snapshot.total_tokens == 0
    assert snapshot.tasks_by_status == {}
