"""Central, idempotent message bus; agents never communicate directly."""

from __future__ import annotations

from app.database.repository import Repository
from app.schemas.models import Message
from app.security.audit_logger import AuditLogger


class MessageBus:
    def __init__(self, repository: Repository, audit: AuditLogger) -> None:
        self.repository = repository
        self.audit = audit

    def publish(self, message: Message) -> bool:
        created = self.repository.save_message(message)
        if created:
            self.audit.record(
                "MESSAGE_PUBLISHED",
                project_id=message.project_id,
                actor_id=message.from_agent,
                task_id=message.task_id,
                payload={"message_id": message.message_id, "type": message.message_type.value},
            )
        return created

    def receive(self, project_id: str, agent_id: str) -> list[Message]:
        return [
            message
            for message in self.repository.list_messages(project_id, to_agent=agent_id)
            if message.status == "PENDING"
        ]

    def acknowledge(self, message_id: str) -> None:
        self.repository.mark_message_delivered(message_id)
