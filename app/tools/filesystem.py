"""Filesystem operations that require a prior PermissionManager decision."""

from __future__ import annotations

from pathlib import Path

from app.schemas.models import Agent, Task
from app.security.permission_manager import PermissionManager


class FileSystemTools:
    def __init__(self, permissions: PermissionManager, max_bytes: int = 1_000_000) -> None:
        self.permissions = permissions
        self.max_bytes = max_bytes

    def read_file(self, workspace: Path, requested: str, agent: Agent, task: Task) -> str:
        target = self.permissions.resolve_authorized_path(
            workspace=workspace, requested=requested, agent=agent, task=task, operation="read"
        )
        if not target.is_file():
            raise FileNotFoundError(requested)
        if target.stat().st_size > self.max_bytes:
            raise ValueError("file exceeds bounded read size")
        return target.read_text(encoding="utf-8")

    def list_directory(
        self, workspace: Path, requested: str, agent: Agent, task: Task
    ) -> list[str]:
        target = self.permissions.resolve_authorized_path(
            workspace=workspace, requested=requested, agent=agent, task=task, operation="list"
        )
        if not target.is_dir():
            raise NotADirectoryError(requested)
        return sorted(item.name for item in target.iterdir())

    def write_file(
        self,
        workspace: Path,
        requested: str,
        content: str,
        agent: Agent,
        task: Task,
        operation: str = "write",
    ) -> None:
        if len(content.encode("utf-8")) > self.max_bytes:
            raise ValueError("file exceeds bounded write size")
        target = self.permissions.resolve_authorized_path(
            workspace=workspace, requested=requested, agent=agent, task=task, operation=operation
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        self.permissions.acquire_lock(
            project_id=agent.project_id,
            task_id=task.task_id,
            agent_id=agent.agent_id,
            resource_path=target.as_posix(),
        )
        try:
            target.write_text(content, encoding="utf-8")
        finally:
            self.permissions.release_lock(target.as_posix(), agent.agent_id)

    def delete_file(self, workspace: Path, requested: str, agent: Agent, task: Task) -> None:
        target = self.permissions.resolve_authorized_path(
            workspace=workspace, requested=requested, agent=agent, task=task, operation="delete"
        )
        if target.is_dir():
            raise IsADirectoryError(requested)
        self.permissions.acquire_lock(
            project_id=agent.project_id,
            task_id=task.task_id,
            agent_id=agent.agent_id,
            resource_path=target.as_posix(),
        )
        try:
            target.unlink(missing_ok=False)
        finally:
            self.permissions.release_lock(target.as_posix(), agent.agent_id)

    def search_workspace(self, workspace: Path, requested: str, query: str, agent: Agent, task: Task) -> list[str]:
        if not query or len(query) > 200:
            raise ValueError("search query must be bounded and non-empty")
        target = self.permissions.resolve_authorized_path(workspace=workspace, requested=requested,
                                                          agent=agent, task=task, operation="search")
        if not target.is_dir():
            raise NotADirectoryError(requested)
        results: list[str] = []
        for path in sorted(item for item in target.rglob("*") if item.is_file() and not item.is_symlink()):
            if len(results) >= 100:
                break
            try:
                if query in path.read_text(encoding="utf-8")[:1_000_000]:
                    results.append(path.relative_to(workspace.resolve()).as_posix())
            except UnicodeDecodeError:
                continue
        return results
