import pytest

from app.orchestrator.engine import PlanValidationError
from app.schemas.models import Architecture, Plan, PlanTask, ProjectRequest


def test_project_creation_initializes_four_agents_and_checkpoint(orchestrator, repository):
    project = orchestrator.create_project(
        ProjectRequest(name="Demo", requirement="Build a task API and UI")
    )
    assert {agent.role for agent in repository.list_agents(project.project_id)} == {
        "planning",
        "frontend",
        "backend",
        "testing",
    }
    assert orchestrator.recover(project.project_id) is not None


def test_plan_validation_rejects_unknown_dependency():
    plan = Plan(
        project_id="PROJECT-test",
        project_brief="brief",
        functional_requirements=["one"],
        non_functional_requirements=["safe"],
        architecture=Architecture(summary="x", components=["api"]),
        tasks=[
            PlanTask(
                task_id="TASK-a",
                title="a",
                description="a",
                assigned_agent="backend",
                dependencies=["missing"],
                acceptance_criteria=["a"],
            )
        ],
    )
    with pytest.raises(PlanValidationError):
        from app.orchestrator.engine import Orchestrator

        Orchestrator.validate_plan(plan)
