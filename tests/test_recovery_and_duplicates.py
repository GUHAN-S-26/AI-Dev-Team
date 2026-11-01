from __future__ import annotations

from pathlib import Path

import pytest

from app.database.repository import Repository
from app.orchestrator.recovery_manager import RecoveryManager
from app.schemas.models import PlanTask, Project, new_id
from app.security.audit_logger import AuditLogger
from app.security.permission_manager import PermissionManager
from app.tasks.task_manager import TaskManager


def test_duplicate_task_ids_are_rejected_and_recovery_reports_abandoned(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "state.sqlite3")
    project = Project(project_id=new_id("PROJECT"), name="Recovery", requirement="Build recovery", root_path=str(tmp_path))
    repository.create_project(project)
    tasks = TaskManager(repository, AuditLogger(repository))
    task = PlanTask(task_id="TASK-unique", title="Work", description="Work", assigned_agent="backend", acceptance_criteria=["done"])
    tasks.create_tasks(project.project_id, [task])
    with pytest.raises(ValueError, match="already exist"):
        tasks.create_tasks(project.project_id, [task])
    recovered = RecoveryManager(repository, PermissionManager(repository, AuditLogger(repository)), AuditLogger(repository))
    assert recovered.reconcile(project.project_id)["abandoned_task_ids"] == []
