"""Derived operational metrics that never expose prompts or credentials."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.database.repository import Repository


class MetricsSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    tasks_by_status: dict[str, int]
    execution_count: int
    failed_executions: int
    tool_calls: int
    failed_tool_calls: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    artifact_count: int


class MonitoringService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def snapshot(self, project_id: str) -> MetricsSnapshot:
        tasks = self.repository.list_tasks(project_id)
        project_executions = [item for item in self.repository.list_executions() if item.project_id == project_id]
        tools = self.repository.list_tool_calls(project_id)
        usage = self.repository.usage_summary(project_id)
        return MetricsSnapshot(
            project_id=project_id,
            tasks_by_status={status: sum(task.status.value == status for task in tasks) for status in {task.status.value for task in tasks}},
            execution_count=len(project_executions),
            failed_executions=sum(item.status == "FAILED" for item in project_executions),
            tool_calls=len(tools),
            failed_tool_calls=sum(item["status"] != "SUCCEEDED" for item in tools),
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
            artifact_count=len(self.repository.list_artifacts(project_id)),
        )

    def export(self, project_id: str) -> dict[str, Any]:
        return self.snapshot(project_id).model_dump(mode="json")
