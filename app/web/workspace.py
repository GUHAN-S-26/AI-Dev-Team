"""Chat-first project workspace orchestration services for the web surface."""

from __future__ import annotations

import asyncio
import shutil
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from app.ai.azure_client import AzureClientError, AzureOpenAIClient
from app.config import Settings
from app.database.repository import Repository
from app.observability.monitor import MonitoringService
from app.orchestrator.engine import Orchestrator
from app.schemas.models import ChatMessage, ProjectStatus, TaskStatus
from app.security.audit_logger import AuditLogger
from app.web.preview import PreviewManager


class ProjectDeletionError(RuntimeError):
    """Raised when a project cannot be removed safely."""


class WorkspaceService:
    """Coordinates project chat and bounded workflow jobs.

    HTTP handlers remain short and deterministic. Long-running Azure, agent,
    Docker, and QA operations run in a bounded executor and communicate back
    through persisted project chat/activity records.
    """

    def __init__(self, settings: Settings, repository: Repository) -> None:
        self.settings = settings
        self.repository = repository
        self.audit = AuditLogger(repository)
        self.monitor = MonitoringService(repository)
        self.preview = PreviewManager(settings, repository)
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="workspace")
        self._jobs: dict[str, Future[None]] = {}
        self._lock = threading.RLock()

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)

    def delete_project(self, project_id: str) -> str:
        """Stop and remove one project across runtime, files, and SQLite.

        Every filesystem target is resolved and must be the exact child named
        by the project ID under its dedicated configured root. This prevents a
        malformed database path or project ID from turning a project deletion
        into a broad host deletion. Running workflows are rejected so a worker
        cannot recreate files after the cleanup completes.
        """
        project = self.repository.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        with self._lock:
            current = self._jobs.get(project_id)
            if current is not None and not current.done():
                raise ProjectDeletionError("project workflow is still running")

            targets = [
                self._confined_project_path(
                    Path(project.root_path), self.settings.projects_dir, project_id, "project"
                ),
                self._confined_project_path(
                    self.settings.workspaces_dir / project_id,
                    self.settings.workspaces_dir,
                    project_id,
                    "worktree",
                ),
                self._confined_project_path(
                    self.settings.data_dir / "artifacts" / project_id,
                    self.settings.data_dir / "artifacts",
                    project_id,
                    "artifact",
                ),
            ]
            # Stop first so a published loopback port and preview container do
            # not survive removal of their mounted project workspace.
            self.preview.stop(project_id)
            for target in {target for target in targets if target.exists()}:
                if not target.is_dir():
                    raise ProjectDeletionError(f"{target.name} storage is not a directory")
                shutil.rmtree(target)
            if not self.repository.delete_project(project_id):
                raise KeyError(project_id)
        return project.name

    @staticmethod
    def _confined_project_path(
        candidate: Path, configured_root: Path, project_id: str, label: str
    ) -> Path:
        root = configured_root.resolve()
        target = candidate.resolve()
        expected = (root / project_id).resolve()
        if target != expected or target == root or root not in target.parents:
            raise ProjectDeletionError(f"{label} storage is outside its project root")
        return target

    def _orchestrator(self) -> Orchestrator:
        try:
            client = AzureOpenAIClient(self.settings)
        except AzureClientError:
            client = None
        return Orchestrator(self.settings, self.repository, client)

    def _message(self, project_id: str, user_id: str, role: str, content: str, metadata: dict[str, Any] | None = None) -> ChatMessage:
        message = ChatMessage(
            project_id=project_id,
            user_id=user_id,
            role=role,  # type: ignore[arg-type]
            content=content[:200_000],
            metadata=metadata or {},
        )
        self.repository.save_chat_message(message)
        return message

    def _event(self, project_id: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        self._message(project_id, "orchestrator", "event", content, metadata)

    def _assistant(self, project_id: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        self._message(project_id, "orchestrator", "assistant", content, metadata)

    def _submit(self, project_id: str, work: Callable[[], None]) -> bool:
        with self._lock:
            current = self._jobs.get(project_id)
            if current is not None and not current.done():
                return False
            self._jobs[project_id] = self._executor.submit(work)
            return True

    def chat(self, project_id: str, user_id: str, content: str) -> dict[str, Any]:
        text = content.strip()
        if not text or len(text) > 100_000:
            raise ValueError("chat message must contain 1-100000 characters")
        project = self.repository.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        self._message(project_id, user_id, "user", text)
        self.audit.record("CHAT_MESSAGE_CREATED", project_id=project_id, actor_id=user_id, payload={"length": len(text)})
        if project.status is ProjectStatus.CREATED:
            project.requirement = project.requirement + "\n\nAdditional user direction:\n" + text
            self.repository.update_project(project)
            if self._submit(project_id, lambda: self._plan(project_id)):
                self._event(project_id, "Planning Agent started from project chat.", {"stage": "planning"})
            else:
                self._assistant(project_id, "A project workflow is already running. I saved your message to this project context.")
        elif project.status is ProjectStatus.AWAITING_APPROVAL:
            self._assistant(project_id, "The plan is ready for your approval. Review the plan card, then approve it to start the agents.")
        elif project.status in {ProjectStatus.DEVELOPMENT, ProjectStatus.INTEGRATION, ProjectStatus.QA}:
            self._assistant(project_id, "Your direction is saved in this project chat. The current workflow will finish its controlled stage before acting on new work.")
        else:
            self._assistant(project_id, "Your message is saved in this project conversation.")
        return self.workspace(project_id)

    def _plan(self, project_id: str) -> None:
        try:
            self._event(project_id, "Planning Agent is analyzing requirements.", {"stage": "planning"})
            orchestrator = self._orchestrator()
            plan = asyncio.run(orchestrator.generate_plan(project_id))
            approval_id = orchestrator.request_plan_approval(project_id)
            self._assistant(
                project_id,
                "The Planning Agent produced a validated plan. Human approval is required before implementation begins.",
                {"stage": "planning", "approval_id": approval_id, "plan": plan.model_dump(mode="json")},
            )
            self._event(project_id, "Plan approval requested.", {"approval_id": approval_id})
        except Exception as error:  # noqa: BLE001 - persist bounded workflow failure
            self._assistant(project_id, "Planning could not complete. Check the configuration and activity details, then retry.", {"stage": "planning", "error": str(error)[:500]})
            self._event(project_id, "Planning failed.", {"stage": "planning"})

    def decide_approval(self, approval_id: str, user_id: str, approved: bool, reason: str = "") -> dict[str, Any]:
        approval = self.repository.get_approval(approval_id)
        if approval is None:
            raise KeyError(approval_id)
        orchestrator = self._orchestrator()
        if approval.action == "approve_plan":
            orchestrator.approve_plan(approval_id, user_id, approved, reason[:1000])
            if approved:
                self._assistant(approval.project_id, "Plan approved. Frontend, Backend, and Testing workflows are queued.", {"stage": "development"})
                self._submit(approval.project_id, lambda: self._develop(approval.project_id))
            else:
                self._assistant(approval.project_id, "Plan rejected. Update the project conversation and request a new plan.")
        else:
            orchestrator.approvals.decide(approval_id, user_id, approved, reason[:1000])
            if approved and approval.action == "merge_to_main":
                self._assistant(approval.project_id, "Integration approved. The orchestrator is merging validated worktrees and running QA.", {"stage": "integration"})
                self._submit(approval.project_id, lambda: self._integrate_and_qa(approval.project_id))
            elif not approved:
                self._assistant(approval.project_id, "The requested integration action was rejected and no merge was performed.")
        return self.workspace(approval.project_id)

    def _develop(self, project_id: str) -> None:
        try:
            self._event(project_id, "Frontend, Backend, and Testing agents are executing in isolated worktrees.", {"stage": "development"})
            orchestrator = self._orchestrator()
            asyncio.run(orchestrator.run_development(project_id))
            approval_id = orchestrator.request_integration(project_id)
            self._assistant(project_id, "Development completed. Review the integration approval before merging the isolated worktrees.", {"stage": "integration", "approval_id": approval_id})
            self._event(project_id, "Integration approval requested.", {"approval_id": approval_id})
        except Exception as error:  # noqa: BLE001 - persist bounded workflow failure
            self._assistant(project_id, "Development stopped after an execution failure. Review Agent Activity for the bounded error and retry after fixing it.", {"stage": "development", "error": str(error)[:500]})
            self._event(project_id, "Development failed.", {"stage": "development"})

    def _integrate_and_qa(self, project_id: str) -> None:
        try:
            orchestrator = self._orchestrator()
            commits = orchestrator.integrate(project_id)
            self._event(project_id, "Approved worktrees merged into the project repository.", {"stage": "integration", "commits": commits})
            report = orchestrator.run_final_qa(project_id)
            self._assistant(project_id, f"QA completed with status {report.status}. Browser evidence and the live preview can now be opened from the right panel.", {"stage": "qa", "status": report.status})
            if report.status == "PASS":
                preview = self.preview.start(project_id)
                self._event(project_id, "Project preview runtime started." if preview.status == "RUNNING" else "Project preview runtime failed to start.", {"stage": "preview", "status": preview.status})
                if preview.status == "RUNNING":
                    try:
                        browser = orchestrator.run_browser_qa(project_id, ["python", "backend/server.py"])
                        self._assistant(project_id, f"Browser QA finished with status {browser.status}. The tested application is available in Live Preview.", {"stage": "browser-qa", "status": browser.status})
                        if browser.status in {"PASS", "BASELINE_CREATED"}:
                            orchestrator.deliver(project_id)
                    except Exception as error:  # noqa: BLE001 - browser QA is recorded as workflow evidence
                        self._event(project_id, "Browser QA could not complete.", {"stage": "browser-qa", "error": str(error)[:500]})
        except Exception as error:  # noqa: BLE001 - persist bounded workflow failure
            self._assistant(project_id, "Integration or QA stopped after a controlled failure. Review the QA and Agent Activity tabs.", {"stage": "integration", "error": str(error)[:500]})
            self._event(project_id, "Integration or QA failed.", {"stage": "integration"})

    def _agent_views(self, project_id: str, tasks: list[Any]) -> list[dict[str, Any]]:
        """Build truthful dashboard status from persisted task state.

        Agent records describe authorization and configuration. The scheduler
        owns task state, so the dashboard derives the user-facing status from
        those persisted task transitions instead of displaying stale creation
        state from the agent record.
        """
        weights = {
            TaskStatus.COMPLETED: 100,
            TaskStatus.REVIEW: 80,
            TaskStatus.IN_PROGRESS: 50,
            TaskStatus.ASSIGNED: 25,
            TaskStatus.FAILED: 0,
            TaskStatus.CANCELLED: 0,
            TaskStatus.PENDING: 0,
            TaskStatus.BLOCKED: 0,
        }
        views: list[dict[str, Any]] = []
        for agent in self.repository.list_agents(project_id):
            owned = [task for task in tasks if task.assigned_agent == agent.role]
            active = next(
                (
                    task
                    for task in owned
                    if task.status
                    in {TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW}
                ),
                None,
            )
            next_task = active or next(
                (task for task in owned if task.status not in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}),
                None,
            )
            if any(task.status is TaskStatus.FAILED for task in owned):
                status = "Failed"
            elif active is not None:
                status = "Running"
            elif owned and all(task.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED} for task in owned):
                status = "Completed"
            else:
                status = "Idle"
            percentage = (
                round(sum(weights[task.status] for task in owned) / len(owned))
                if owned
                else 0
            )
            views.append(
                {
                    **agent.model_dump(mode="json"),
                    "status": status,
                    "raw_status": agent.status.value,
                    "current_task": next_task.title if next_task else None,
                    "current_task_status": next_task.status.value if next_task else None,
                    "task_count": len(owned),
                    "completed_tasks": sum(task.status is TaskStatus.COMPLETED for task in owned),
                    "progress_percentage": percentage,
                }
            )
        return views

    def workspace(self, project_id: str) -> dict[str, Any]:
        project = self.repository.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        tasks = self.repository.list_tasks(project_id)
        executions = [
            execution.model_dump(mode="json")
            for execution in self.repository.list_executions()
            if execution.project_id == project_id
        ]
        completed_tasks = sum(task.status is TaskStatus.COMPLETED for task in tasks)
        progress_percentage = round(completed_tasks / len(tasks) * 100) if tasks else 0
        return {
            "project": project.model_dump(mode="json"),
            "chat": [message.model_dump(mode="json") for message in self.repository.list_chat_messages(project_id)],
            "agents": self._agent_views(project_id, tasks),
            "tasks": [task.model_dump(mode="json") for task in tasks],
            "executions": executions,
            "task_progress": {
                "total": len(tasks),
                "completed": completed_tasks,
                "percentage": progress_percentage,
            },
            "approvals": [approval.model_dump(mode="json") for approval in self.repository.list_approvals(project_id)],
            "activity": self.repository.list_audit_events(project_id, 100),
            "artifacts": self.repository.list_artifacts(project_id),
            "tool_calls": self.repository.list_tool_calls(project_id, 100),
            "metrics": self.monitor.export(project_id),
            "preview": self.preview.status(project_id).model_dump(mode="json"),
            "workflow_running": bool(self._jobs.get(project_id) and not self._jobs[project_id].done()),
        }
