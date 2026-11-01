"""Primary-agent definitions; agents propose, the orchestrator decides."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from app.runtime.agent_runtime import AgentRuntime
from app.schemas.models import Agent, Task


@dataclass(frozen=True)
class AgentDefinition:
    role: str
    instruction_version: str
    system_prompt: str
    allowed_tools: tuple[str, ...]
    authorized_paths: tuple[str, ...]

    async def execute(
        self, runtime: AgentRuntime, agent: Agent, task: Task, output_model: type[BaseModel]
    ) -> BaseModel:
        return await runtime.invoke(
            agent=agent, task=task, system_prompt=self.system_prompt, output_model=output_model
        )
