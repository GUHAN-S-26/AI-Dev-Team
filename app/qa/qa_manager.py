"""Independent QA coordination and bounded defect conversion."""

from __future__ import annotations

from pathlib import Path

from app.qa.playwright_runner import PlaywrightReport, PlaywrightRunner
from app.qa.test_runner import TestRunner
from app.schemas.models import BugReport, PlanTask, Task, TestReport
from app.tasks.task_manager import TaskManager


class QAManager:
    def __init__(self, runner: TestRunner, tasks: TaskManager) -> None:
        self.runner = runner
        self.tasks = tasks

    def run_final_suite(self, workspace: Path) -> TestReport:
        return self.runner.run_pytest(workspace)

    def create_repair_task(self, bug: BugReport) -> Task:
        repair = PlanTask(
            task_id=f"REPAIR-{bug.bug_id}",
            title=f"Repair {bug.bug_id}: {bug.suspected_component}",
            description=(f"{bug.actual_behavior}\nReproduction:\n" + "\n".join(bug.reproduction_steps)),
            assigned_agent=bug.assigned_owner,
            dependencies=[],
            acceptance_criteria=["Reproduction no longer fails", "Relevant regression test passes"],
            authorized_paths=[f"{bug.suspected_component}/**"],
        )
        return self.tasks.create_tasks(bug.project_id, [repair])[0]

    def run_browser_suite(
        self,
        runner: PlaywrightRunner,
        project_id: str,
        workspace: Path,
        start_command: list[str],
        readiness_url: str = "http://127.0.0.1:8000/",
    ) -> PlaywrightReport:
        return runner.run(
            project_id,
            workspace,
            start_command=start_command,
            readiness_url=readiness_url,
        )
