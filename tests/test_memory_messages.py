import pytest

from app.communication.message_bus import MessageBus
from app.memory.memory_manager import MemoryAccessError, MemoryManager
from app.schemas.models import MemoryEntry, Message, MessageType, Project
from app.security.audit_logger import AuditLogger


def test_private_memory_isolated_and_messages_idempotent(repository):
    project = Project(
        project_id="PROJECT-memory",
        name="memory",
        requirement="a valid requirement here",
        root_path="/tmp/project",
    )
    repository.create_project(project)
    memory = MemoryManager(repository)
    entry = MemoryEntry(
        project_id=project.project_id,
        namespace="private:backend",
        owner_agent_id="backend",
        content={"lesson": "bounded"},
    )
    memory.write_private(entry, "backend")
    assert len(memory.read_private(project.project_id, "backend", "private:backend")) == 1
    assert memory.read_private(project.project_id, "frontend", "private:backend") == []
    with pytest.raises(MemoryAccessError):
        memory.write_private(entry, "frontend")
    bus = MessageBus(repository, AuditLogger(repository))
    message = Message(
        from_agent="backend",
        to_agent="testing",
        project_id=project.project_id,
        message_type=MessageType.TASK_COMPLETED,
        content={"ok": True},
        idempotency_key="once",
    )
    assert bus.publish(message) is True
    assert bus.publish(message) is False
    assert len(bus.receive(project.project_id, "testing")) == 1
    bus.acknowledge(message.message_id)
    assert bus.receive(project.project_id, "testing") == []
