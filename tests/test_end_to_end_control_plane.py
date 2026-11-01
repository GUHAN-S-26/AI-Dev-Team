from __future__ import annotations

import pytest

from app.ai.azure_client import ModelUsage
from app.schemas.models import AgentWorkResult, Architecture, Plan, PlanTask, ProjectRequest


class FakeAzureClient:
    """Deterministic test double for the Azure boundary; production injects AzureOpenAIClient."""

    async def complete_json(self, *, system, user, response_model, project_id, task_id=None):
        del system, user, task_id
        if response_model is Plan:
            output = Plan(
                project_id=project_id,
                project_brief="A small full-stack task app",
                functional_requirements=["Users can create tasks"],
                non_functional_requirements=["Validate all inputs"],
                architecture=Architecture(summary="API plus web client", components=["backend", "frontend"]),
                tasks=[
                    PlanTask(task_id="TASK-backend", title="Backend", description="Build API",
                             assigned_agent="backend", acceptance_criteria=["API tests pass"],
                             authorized_paths=["backend/**"]),
                    PlanTask(task_id="TASK-frontend", title="Frontend", description="Build UI",
                             assigned_agent="frontend", acceptance_criteria=["UI builds"],
                             authorized_paths=["frontend/**"]),
                    PlanTask(task_id="TASK-testing", title="Tests", description="Test app",
                             assigned_agent="testing", acceptance_criteria=["QA report exists"],
                             authorized_paths=["tests/**"]),
                ],
            )
        else:
            output = AgentWorkResult(summary="validated test work", completed=True)
        return output, ModelUsage(10, 10, 20, 1.0, "test-deployment")


@pytest.mark.asyncio
async def test_plan_approval_and_parallel_development(orchestrator, repository):
    orchestrator.client = FakeAzureClient()
    from app.runtime.agent_runtime import AgentRuntime

    orchestrator.runtime = AgentRuntime(FakeAzureClient(), repository, orchestrator.memory,
                                        orchestrator.messages, orchestrator.audit,
                                        orchestrator.settings.max_task_tokens,
                                        orchestrator.settings.max_project_tokens)
    project = orchestrator.create_project(ProjectRequest(name="Full stack", requirement="Build a task app"))
    plan = await orchestrator.generate_plan(project.project_id)
    assert len(plan.tasks) == 3
    approval_id = orchestrator.request_plan_approval(project.project_id)
    orchestrator.approve_plan(approval_id, "human-reviewer", True)
    assert len(repository.list_tasks(project.project_id)) == 3
    await orchestrator.run_development(project.project_id)
    assert all(task.status.value == "COMPLETED" for task in repository.list_tasks(project.project_id))
    assert len(repository.list_executions()) == 3
