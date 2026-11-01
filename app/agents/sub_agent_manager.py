"""Permission-controlled, bounded sub-agent lifecycle."""

from __future__ import annotations

from typing import ClassVar

from app.database.repository import Repository
from app.schemas.models import Agent, AgentStatus, SubAgentRequest, new_id
from app.security.audit_logger import AuditLogger


class SubAgentManager:
    ALLOWED_ROLES: ClassVar[set[str]] = {
        "Requirement Analyst",
        "System Architect",
        "API Designer",
        "Database Designer",
        "UI Developer",
        "Component Developer",
        "Integration Developer",
        "UI Reviewer",
        "API Developer",
        "Database Developer",
        "Security Developer",
        "Business Logic Developer",
        "Unit Testing Agent",
        "API Testing Agent",
        "Integration Testing Agent",
        "Regression Testing Agent",
    }

    def __init__(self, repository: Repository, audit: AuditLogger) -> None:
        self.repository = repository
        self.audit = audit

    def create(self, request: SubAgentRequest) -> Agent:
        parent = next(
            (
                agent
                for agent in self.repository.list_agents(request.project_id)
                if agent.agent_id == request.parent_agent_id
            ),
            None,
        )
        if parent is None:
            raise PermissionError("parent agent does not exist")
        if parent.parent_agent_id is not None:
            raise PermissionError("sub-agents cannot create further sub-agents")
        if request.role not in self.ALLOWED_ROLES:
            raise PermissionError("sub-agent role is not allowed")
        active = [
            agent
            for agent in self.repository.list_agents(request.project_id)
            if agent.parent_agent_id == parent.agent_id
            and agent.status in {AgentStatus.CREATED, AgentStatus.ASSIGNED, AgentStatus.RUNNING}
        ]
        if len(active) >= 3:
            raise PermissionError("maximum active sub-agents per primary agent exceeded")
        agent = Agent(
            agent_id=new_id("SUBAGENT"),
            role=request.role,
            project_id=request.project_id,
            parent_agent_id=parent.agent_id,
            task_id=request.task_id,
            private_memory_namespace=f"private:{new_id('NS')}",
            authorized_paths=request.authorized_paths,
            allowed_tools=request.allowed_tools,
            max_tokens=request.max_tokens,
        )
        self.repository.save_agent(agent)
        self.audit.record(
            "SUB_AGENT_CREATED",
            project_id=request.project_id,
            actor_id=parent.agent_id,
            task_id=request.task_id,
            payload={"agent_id": agent.agent_id, "role": agent.role},
        )
        return agent
