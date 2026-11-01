"""Canonical path, ownership, tool, and lock authorization."""

from __future__ import annotations

import fnmatch
import time
from pathlib import Path

from app.database.repository import Repository
from app.schemas.models import Agent, Task, new_id
from app.security.audit_logger import AuditLogger


class AuthorizationError(PermissionError):
    pass


class PermissionManager:
    def __init__(self, repository: Repository, audit: AuditLogger) -> None:
        self.repository = repository
        self.audit = audit

    @staticmethod
    def _safe_relative(workspace: Path, requested: str) -> Path:
        if not requested or "\x00" in requested:
            raise AuthorizationError("invalid path")
        candidate = Path(requested)
        if candidate.is_absolute():
            raise AuthorizationError("absolute paths are not accepted")
        resolved_workspace = workspace.resolve()
        resolved_target = (resolved_workspace / candidate).resolve(strict=False)
        try:
            resolved_target.relative_to(resolved_workspace)
        except ValueError as error:
            raise AuthorizationError("path escapes authorized workspace") from error
        return resolved_target

    def resolve_authorized_path(
        self, *, workspace: Path, requested: str, agent: Agent, task: Task, operation: str
    ) -> Path:
        target = self._safe_relative(workspace, requested)
        relative = target.relative_to(workspace.resolve()).as_posix()
        allowed = list(agent.authorized_paths) + list(task.authorized_paths)
        if not allowed or not any(fnmatch.fnmatch(relative, pattern) for pattern in allowed):
            self.audit.record(
                "FILE_OPERATION_DENIED",
                project_id=agent.project_id,
                actor_id=agent.agent_id,
                task_id=task.task_id,
                payload={"operation": operation, "path": relative, "reason": "ownership"},
            )
            raise AuthorizationError(f"{agent.agent_id} does not own {relative}")
        for owner, pattern, shared in self.repository.list_file_ownership(agent.project_id):
            if fnmatch.fnmatch(relative, pattern) and owner != agent.agent_id and not shared:
                raise AuthorizationError(f"path is owned by {owner}: {relative}")
        return target

    def acquire_lock(
        self,
        *,
        project_id: str,
        task_id: str,
        agent_id: str,
        resource_path: str,
        ttl_seconds: int = 300,
    ) -> None:
        now = time.time()
        expires = now + ttl_seconds
        with self.repository.transaction() as db:
            row = db.execute(
                "SELECT owner_agent_id, expires_at FROM file_locks WHERE resource_path=?",
                (resource_path,),
            ).fetchone()
            if row and float(row[1]) > now and row[0] != agent_id:
                raise AuthorizationError(f"resource lock held by {row[0]}")
            db.execute(
                "INSERT OR REPLACE INTO file_locks(resource_path, project_id, task_id, owner_agent_id, acquired_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (resource_path, project_id, task_id, agent_id, str(now), str(expires)),
            )
        self.audit.record(
            "FILE_LOCK_ACQUIRED",
            project_id=project_id,
            actor_id=agent_id,
            task_id=task_id,
            payload={"resource_path": resource_path, "expires_at": expires},
        )

    def release_lock(self, resource_path: str, agent_id: str) -> None:
        with self.repository.transaction() as db:
            db.execute(
                "DELETE FROM file_locks WHERE resource_path=? AND owner_agent_id=?",
                (resource_path, agent_id),
            )
        self.audit.record(
            "FILE_LOCK_RELEASED", actor_id=agent_id, payload={"resource_path": resource_path}
        )

    def expire_locks(self) -> int:
        with self.repository.transaction() as db:
            cursor = db.execute(
                "DELETE FROM file_locks WHERE CAST(expires_at AS REAL) <= ?", (time.time(),)
            )
            return cursor.rowcount

    def set_ownership(
        self, *, project_id: str, agent_id: str, pattern: str, shared: bool = False
    ) -> str:
        if pattern.startswith("/") or ".." in Path(pattern).parts:
            raise AuthorizationError("ownership pattern must be relative")
        ownership_id = new_id("OWN")
        self.repository.set_file_ownership(ownership_id, project_id, agent_id, pattern, shared)
        return ownership_id
