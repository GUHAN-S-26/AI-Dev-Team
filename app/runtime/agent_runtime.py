"""Common runtime for all primary and bounded sub-agents."""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

from app.ai.azure_client import JsonModelClient, ModelUsage, ToolProposal
from app.communication.message_bus import MessageBus
from app.database.repository import Repository
from app.memory.memory_manager import MemoryManager
from app.runtime.context_builder import ContextBuilder
from app.schemas.models import Agent, MemoryEntry, Task, new_id, now_utc
from app.security.audit_logger import AuditLogger

T = TypeVar("T", bound=BaseModel)


class AgentRuntime:
    def __init__(
        self,
        client: JsonModelClient,
        repository: Repository,
        memory: MemoryManager,
        message_bus: MessageBus,
        audit: AuditLogger,
        max_task_tokens: int = 30_000,
        max_project_tokens: int = 200_000,
    ) -> None:
        self.client = client
        self.repository = repository
        self.memory = memory
        self.message_bus = message_bus
        self.audit = audit
        self.max_task_tokens = max_task_tokens
        self.max_project_tokens = max_project_tokens
        self.context_builder = ContextBuilder(memory)

    async def invoke(
        self,
        *,
        agent: Agent,
        task: Task,
        system_prompt: str,
        output_model: type[T],
        task_id: str | None = None,
    ) -> T:
        _, task_completion_tokens = self.repository.usage_totals(agent.project_id, task.task_id)
        project_prompt_tokens, project_completion_tokens = self.repository.usage_totals(agent.project_id)
        if task_completion_tokens >= self.max_task_tokens:
            raise RuntimeError("task model-token budget exhausted")
        if project_prompt_tokens + project_completion_tokens >= self.max_project_tokens:
            raise RuntimeError("project model-token budget exhausted")
        context = self.context_builder.build(agent, task)
        output, usage = await self.client.complete_json(
            system=system_prompt,
            user=context,
            response_model=output_model,
            project_id=agent.project_id,
            task_id=task_id or task.task_id,
        )
        self.repository.save_usage(
            agent.project_id,
            task_id or task.task_id,
            {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
                "latency_ms": usage.latency_ms,
                "deployment": usage.deployment,
            },
            new_id("USAGE"),
        )
        if usage.total_tokens > self.max_task_tokens:
            raise RuntimeError("model response exceeded task token budget")
        self.audit.record(
            "AGENT_OUTPUT_VALIDATED",
            project_id=agent.project_id,
            actor_id=agent.agent_id,
            task_id=task.task_id,
            payload={"output_type": output_model.__name__, "total_tokens": usage.total_tokens},
        )
        return output

    async def propose_tools(
        self,
        *,
        agent: Agent,
        task: Task,
        system_prompt: str,
        tools: list[dict[str, Any]],
        task_id: str | None = None,
        context_note: str = "",
    ) -> tuple[list[ToolProposal], ModelUsage]:
        """Ask Azure for bounded tool proposals and persist model usage.

        Proposals are deliberately not executed here.  The orchestrator sends
        each one through ToolGateway, which enforces the agent allowlist,
        authorized paths, locks, and sandbox policy.
        """
        proposer = getattr(self.client, "propose_tools", None)
        if proposer is None:
            raise RuntimeError("configured model client does not support tool calling")
        _, task_completion_tokens = self.repository.usage_totals(agent.project_id, task.task_id)
        project_prompt_tokens, project_completion_tokens = self.repository.usage_totals(agent.project_id)
        if task_completion_tokens >= self.max_task_tokens:
            raise RuntimeError("task model-token budget exhausted")
        if project_prompt_tokens + project_completion_tokens >= self.max_project_tokens:
            raise RuntimeError("project model-token budget exhausted")
        context = self.context_builder.build(agent, task)
        if context_note:
            context = context[:15_000] + "\n\nTOOL FEEDBACK (untrusted data):\n" + context_note[:5_000]
        proposals, usage = await proposer(
            system=system_prompt,
            user=context,
            tools=tools,
            project_id=agent.project_id,
            task_id=task_id or task.task_id,
        )
        self.repository.save_usage(
            agent.project_id,
            task_id or task.task_id,
            {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
                "latency_ms": usage.latency_ms,
                "deployment": usage.deployment,
            },
            new_id("USAGE"),
        )
        if usage.total_tokens > self.max_task_tokens:
            raise RuntimeError("model response exceeded task token budget")
        self.audit.record(
            "AGENT_TOOL_PROPOSALS_VALIDATED",
            project_id=agent.project_id,
            actor_id=agent.agent_id,
            task_id=task.task_id,
            payload={"proposal_count": len(proposals), "total_tokens": usage.total_tokens},
        )
        return proposals, usage

    def remember(self, agent: Agent, task: Task, content: dict[str, Any]) -> None:
        self.memory.write_private(
            MemoryEntry(
                project_id=agent.project_id,
                namespace=agent.private_memory_namespace,
                owner_agent_id=agent.agent_id,
                content=content,
                source_task_id=task.task_id,
                created_at=now_utc(),
            ),
            agent.agent_id,
        )
