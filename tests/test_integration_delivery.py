from pathlib import Path

import pytest

from app.schemas.models import (
    Architecture,
    MemoryEntry,
    Plan,
    PlanTask,
    ProjectRequest,
    new_id,
)
from app.schemas.models import TestReport as _TestReport

QAReport = _TestReport


def test_integration_requires_approval_and_delivery_is_persisted(orchestrator, repository):
    project = orchestrator.create_project(ProjectRequest(name="Merge", requirement="Build a mergeable app"))
    for role in ("frontend", "backend", "testing"):
        orchestrator.workspaces.create_agent_worktree(project.project_id, role, Path(project.root_path))
    approval_id = orchestrator.request_integration(project.project_id)
    with pytest.raises(PermissionError):
        orchestrator.integrate(project.project_id)
    orchestrator.approvals.decide(approval_id, "release-reviewer", True)
    commits = orchestrator.integrate(project.project_id)
    assert len(commits) == 3
    plan = Plan(project_id=project.project_id, project_brief="brief", functional_requirements=["feature"],
                non_functional_requirements=["safe"],
                architecture=Architecture(summary="architecture", components=["api"]),
                tasks=[PlanTask(title="backend", description="b", assigned_agent="backend",
                                acceptance_criteria=["works"])])
    repository.save_project_memory(MemoryEntry(project_id=project.project_id, namespace="approved-plan",
                                               owner_agent_id="orchestrator", content=plan.model_dump(mode="json"),
                                               approved=True))
    repository.save_artifact(new_id("ARTIFACT"), project.project_id, "qa-report", "testing/report.json",
                             QAReport(suite_name="pytest", status="PASS", passed=1).model_dump(mode="json"))
    report_path = orchestrator.deliver(project.project_id)
    assert report_path.is_file()
    assert repository.get_project(project.project_id).status.value == "COMPLETED"
