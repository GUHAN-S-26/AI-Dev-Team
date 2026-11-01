"""Policy-controlled memory access."""

from __future__ import annotations

from app.database.repository import Repository
from app.schemas.models import MemoryEntry


class MemoryAccessError(PermissionError):
    pass


class MemoryManager:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def write_private(self, entry: MemoryEntry, actor_agent_id: str) -> None:
        if entry.owner_agent_id != actor_agent_id or not entry.namespace.startswith("private:"):
            raise MemoryAccessError("agents may write only their own private memory namespace")
        self.repository.save_agent_memory(entry)

    def write_shared(self, entry: MemoryEntry, actor_agent_id: str) -> None:
        if actor_agent_id != "orchestrator":
            raise MemoryAccessError("shared project memory writes require orchestrator mediation")
        if entry.owner_agent_id != actor_agent_id:
            raise MemoryAccessError("shared memory owner must be the orchestrator")
        self.repository.save_project_memory(entry)

    def read_private(self, project_id: str, agent_id: str, namespace: str) -> list[MemoryEntry]:
        if not namespace.startswith("private:"):
            raise MemoryAccessError("private memory namespace required")
        return self.repository.list_memory(project_id, namespace, private_owner=agent_id)

    def read_approved_shared(self, project_id: str, namespace: str) -> list[MemoryEntry]:
        return [
            entry for entry in self.repository.list_memory(project_id, namespace) if entry.approved
        ]
