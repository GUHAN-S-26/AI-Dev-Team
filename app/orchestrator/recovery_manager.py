"""Checkpoint and interruption recovery."""

from __future__ import annotations

from typing import Any

from app.database.repository import Repository
from app.schemas.models import TaskStatus, new_id
from app.security.audit_logger import AuditLogger
from app.security.permission_manager import PermissionManager


class RecoveryManager:
    def __init__(
        self, repository: Repository, permissions: PermissionManager, audit: AuditLogger
    ) -> None:
        self.repository = repository
        self.permissions = permissions
        self.audit = audit

    def checkpoint(self, project_id: str, state: str, payload: dict[str, Any]) -> str:
        checkpoint_id = new_id("CHECKPOINT")
        self.repository.checkpoint(project_id, state, payload, checkpoint_id)
        self.audit.record(
            "WORKFLOW_CHECKPOINT",
            project_id=project_id,
            actor_id="orchestrator",
            payload={"checkpoint_id": checkpoint_id, "state": state},
        )
        return checkpoint_id

    def recover(self, project_id: str) -> tuple[str, dict[str, Any]] | None:
        expired = self.permissions.expire_locks()
        latest = self.repository.latest_checkpoint(project_id)
        reconciliation = self.reconcile(project_id)
        self.audit.record(
            "WORKFLOW_RECOVERY",
            project_id=project_id,
            actor_id="orchestrator",
            payload={"expired_locks": expired, "checkpoint_found": latest is not None, "reconciliation": reconciliation},
        )
        return latest

    def reconcile(self, project_id: str) -> dict[str, Any]:
        """Report abandoned task states without fabricating completion."""
        tasks = self.repository.list_tasks(project_id)
        abandoned = [
            task.task_id
            for task in tasks
            if task.status in {TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW}
        ]
        return {"abandoned_task_ids": abandoned, "completed_task_count": sum(task.status is TaskStatus.COMPLETED for task in tasks)}
