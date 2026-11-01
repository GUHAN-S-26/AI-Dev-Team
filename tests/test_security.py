from pathlib import Path

import pytest

from app.schemas.models import Agent, Task
from app.security.audit_logger import AuditLogger
from app.security.permission_manager import AuthorizationError, PermissionManager
from app.tools.filesystem import FileSystemTools


def make_context(repository, tmp_path: Path):
    from app.schemas.models import Project

    project = Project(
        project_id="PROJECT-security",
        name="security",
        requirement="a valid requirement here",
        root_path=str(tmp_path),
    )
    repository.create_project(project)
    audit = AuditLogger(repository)
    permissions = PermissionManager(repository, audit)
    agent = Agent(
        agent_id="backend",
        role="backend",
        project_id=project.project_id,
        private_memory_namespace="private:backend",
        authorized_paths=["backend/**"],
        allowed_tools=["create_file", "read_file"],
    )
    task = Task(
        project_id=project.project_id,
        title="write",
        description="write",
        assigned_agent="backend",
        acceptance_criteria=["write"],
        authorized_paths=["backend/**"],
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return permissions, agent, task, workspace


def test_path_traversal_and_unauthorized_write_are_rejected(repository, tmp_path):
    permissions, agent, task, workspace = make_context(repository, tmp_path)
    files = FileSystemTools(permissions)
    with pytest.raises(AuthorizationError):
        files.write_file(workspace, "../escape.txt", "no", agent, task)
    with pytest.raises(AuthorizationError):
        files.write_file(workspace, "frontend/app.py", "no", agent, task)


def test_symlink_escape_is_rejected(repository, tmp_path):
    permissions, agent, task, workspace = make_context(repository, tmp_path)
    (workspace / "backend").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / "backend" / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(AuthorizationError):
        FileSystemTools(permissions).write_file(
            workspace, "backend/link/secret.txt", "no", agent, task
        )
