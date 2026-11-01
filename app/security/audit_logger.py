"""Structured, persisted audit events."""

from __future__ import annotations

from typing import Any

from app.database.repository import Repository
from app.schemas.models import new_id


class AuditLogger:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def record(
        self,
        event_type: str,
        *,
        project_id: str | None = None,
        actor_id: str | None = None,
        task_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        event_id = new_id("AUDIT")
        self.repository.audit(
            event_type,
            project_id=project_id,
            actor_id=actor_id,
            task_id=task_id,
            payload=payload or {},
            event_id=event_id,
        )
        return event_id
