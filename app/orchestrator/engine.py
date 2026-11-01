"""Deterministic project lifecycle controller."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.agents.definitions import PRIMARY_DEFINITIONS
from app.agents.sub_agent_manager import SubAgentManager
from app.ai.azure_client import JsonModelClient
from app.communication.message_bus import MessageBus
from app.config import Settings
from app.database.repository import Repository
from app.memory.memory_manager import MemoryManager
from app.orchestrator.delivery import DeliveryManager
from app.orchestrator.integration_manager import IntegrationManager
from app.orchestrator.recovery_manager import RecoveryManager
from app.orchestrator.scheduler import Scheduler
from app.qa.playwright_runner import PlaywrightReport, PlaywrightRunner
from app.qa.qa_manager import QAManager
from app.qa.test_runner import TestRunner
from app.runtime.agent_runtime import AgentRuntime
from app.schemas.models import (
    Agent,
    AgentRole,
    AgentWorkResult,
    BugReport,
    FinalReport,
    MemoryEntry,
    Plan,
    Project,
    ProjectRequest,
    ProjectStatus,
    Task,
    TaskExecution,
    TaskStatus,
    TestReport,
    new_id,
)
from app.security.approval_manager import ApprovalManager
from app.security.audit_logger import AuditLogger
from app.security.permission_manager import PermissionManager
from app.tasks.task_manager import TaskManager
from app.tools.agent_tools import tool_definitions
from app.tools.docker_manager import DockerSandbox
from app.tools.git_manager import GitWorktreeManager
from app.tools.tool_gateway import ToolGateway, ToolRequest
from app.tools.workspace_manager import WorkspaceManager


class PlanValidationError(ValueError):
    pass


class Orchestrator:
    def __init__(
        self, settings: Settings, repository: Repository, client: JsonModelClient | None = None
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.audit = AuditLogger(repository)
        self.permissions = PermissionManager(repository, self.audit)
        self.approvals = ApprovalManager(repository, self.audit)
        self.memory = MemoryManager(repository)
        self.messages = MessageBus(repository, self.audit)
        self.tasks = TaskManager(repository, self.audit)
        self.sub_agents = SubAgentManager(repository, self.audit)
        self.workspaces = WorkspaceManager(settings.projects_dir, settings.workspaces_dir)
        self.integration = IntegrationManager(
            repository, self.approvals, self.audit, settings.require_merge_approval
        )
        self.recovery = RecoveryManager(repository, self.permissions, self.audit)
        self.delivery = DeliveryManager(repository, settings.data_dir / "artifacts")
        self.sandbox = DockerSandbox(
            settings.docker_image, settings.docker_timeout_seconds, settings.max_output_chars
        )
        self.test_runner = TestRunner(self.sandbox)
        self.qa = QAManager(self.test_runner, self.tasks)
        self.tool_gateway = ToolGateway(repository, self.permissions, self.audit, self.sandbox)
        self.client = client
        self.runtime = (
            AgentRuntime(client, repository, self.memory, self.messages, self.audit,
                         settings.max_task_tokens, settings.max_project_tokens)
            if client
            else None
        )

    def create_project(self, request: ProjectRequest) -> Project:
        project_id = new_id("PROJECT")
        root = self.workspaces.initialize_project(project_id)
        project = Project(
            project_id=project_id,
            name=request.name,
            requirement=request.requirement,
            root_path=str(root),
        )
        self.repository.create_project(project)
        for role, definition in PRIMARY_DEFINITIONS.items():
            agent = Agent(
                agent_id=role,
                role=role,
                project_id=project_id,
                private_memory_namespace=f"private:{role}",
                authorized_paths=list(definition.authorized_paths),
                allowed_tools=list(definition.allowed_tools),
                max_tokens=self.settings.max_task_tokens,
            )
            self.repository.save_agent(agent)
            for pattern in definition.authorized_paths:
                self.permissions.set_ownership(
                    project_id=project_id, agent_id=role, pattern=pattern
                )
        self.audit.record(
            "PROJECT_CREATED",
            project_id=project_id,
            actor_id="orchestrator",
            payload={"name": request.name},
        )
        self.recovery.checkpoint(project_id, "CREATED", {"project_id": project_id})
        return project

    async def generate_plan(self, project_id: str) -> Plan:
        if self.runtime is None:
            raise RuntimeError("an Azure OpenAI client is required to generate a plan")
        project = self.repository.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        project.status = ProjectStatus.PLANNING
        project.updated_at = datetime.now(UTC)
        self.repository.update_project(project)
        planning_agent = next(
            agent
            for agent in self.repository.list_agents(project_id)
            if agent.role == AgentRole.PLANNING
        )
        planning_task = Task(
            project_id=project_id,
            title="Analyze requirement and create plan",
            description=project.requirement,
            assigned_agent=planning_agent.agent_id,
            acceptance_criteria=["Produce a complete schema-valid plan"],
            authorized_paths=["docs/**", "architecture/**"],
        )
        plan = await self.runtime.invoke(
            agent=planning_agent,
            task=planning_task,
            system_prompt=PRIMARY_DEFINITIONS["planning"].system_prompt,
            output_model=Plan,
        )
        plan.project_id = project_id
        self.validate_plan(plan)
        self.repository.save_plan(project_id, plan)
        project.status = ProjectStatus.AWAITING_APPROVAL
        project.updated_at = datetime.now(UTC)
        self.repository.update_project(project)
        self.recovery.checkpoint(
            project_id, "PLAN_GENERATED", {"plan": plan.model_dump(mode="json")}
        )
        return plan

    @staticmethod
    def validate_plan(plan: Plan) -> None:
        if not plan.tasks:
            raise PlanValidationError("plan must contain tasks")
        task_ids = {task.task_id for task in plan.tasks}
        if len(task_ids) != len(plan.tasks):
            raise PlanValidationError("plan task IDs must be unique")
        for task in plan.tasks:
            if any(dependency not in task_ids for dependency in task.dependencies):
                raise PlanValidationError(f"unknown dependency in {task.task_id}")
        TaskManager._assert_acyclic(plan.tasks)
        if not plan.architecture.components:
            raise PlanValidationError("architecture must define components")

    def request_plan_approval(self, project_id: str) -> str:
        return self.approvals.request(
            project_id, "approve_plan", {"project_id": project_id}
        ).approval_id

    def approve_plan(
        self, approval_id: str, approver_id: str, approved: bool, reason: str | None = None
    ) -> Project:
        approval = self.approvals.decide(approval_id, approver_id, approved, reason)
        project = self.repository.get_project(approval.project_id)
        if project is None:
            raise KeyError(approval.project_id)
        if approval.action != "approve_plan":
            raise ValueError("approval is not a plan approval")
        if not approved:
            project.status = ProjectStatus.FAILED
            self.repository.update_project(project)
            return project
        latest = self.repository.latest_checkpoint(project.project_id)
        if latest is None or "plan" not in latest[1]:
            raise RuntimeError("no generated plan checkpoint exists")
        plan = Plan.model_validate(latest[1]["plan"])
        self.repository.save_project_memory(
            MemoryEntry(
                project_id=project.project_id,
                namespace="approved-plan",
                owner_agent_id="orchestrator",
                content=plan.model_dump(mode="json"),
                approved=True,
            )
        )
        created_tasks = self.tasks.create_tasks(project.project_id, plan.tasks)
        for planning_task in created_tasks:
            if planning_task.assigned_agent != AgentRole.PLANNING.value:
                continue
            self.tasks.transition(planning_task.task_id, TaskStatus.ASSIGNED, "orchestrator")
            self.tasks.transition(planning_task.task_id, TaskStatus.IN_PROGRESS, "orchestrator")
            self.tasks.transition(planning_task.task_id, TaskStatus.REVIEW, "orchestrator")
            self.tasks.transition(planning_task.task_id, TaskStatus.COMPLETED, "orchestrator")
        project.status = ProjectStatus.DEVELOPMENT
        project.updated_at = datetime.now(UTC)
        self.repository.update_project(project)
        self.recovery.checkpoint(project.project_id, "PLAN_APPROVED", {"approval_id": approval_id})
        return project

    async def run_development(self, project_id: str) -> None:
        if self.runtime is None:
            raise RuntimeError("an Azure OpenAI client is required for development")
        project = self.repository.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        for agent in self.repository.list_agents(project_id):
            definition = PRIMARY_DEFINITIONS.get(agent.role)
            if definition is not None:
                agent.authorized_paths = sorted(
                    set(agent.authorized_paths) | set(definition.authorized_paths)
                )
                self.repository.save_agent(agent)
        for role in ("frontend", "backend", "testing"):
            try:
                self.workspaces.create_agent_worktree(project_id, role, Path(project.root_path))
            except Exception as error:
                self.audit.record(
                    "WORKTREE_CREATE_FAILED",
                    project_id=project_id,
                    actor_id="orchestrator",
                    payload={"role": role, "error": str(error)},
                )
                raise
        self._recover_interrupted_tasks(project_id)
        scheduler = Scheduler(self.settings.max_concurrency)
        await scheduler.run(self.repository.list_tasks(project_id), self._execute_task)
        project.status = ProjectStatus.INTEGRATION
        project.updated_at = datetime.now(UTC)
        self.repository.update_project(project)
        self.recovery.checkpoint(project_id, "DEVELOPMENT_COMPLETE", {})

    def _recover_interrupted_tasks(self, project_id: str) -> None:
        """Return unfinished persisted executions to the bounded retry queue."""
        for task in self.repository.list_tasks(project_id):
            if task.status in {TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW}:
                if task.status is TaskStatus.ASSIGNED or task.status is TaskStatus.REVIEW:
                    self.tasks.transition(task.task_id, TaskStatus.IN_PROGRESS, "recovery")
                self.tasks.transition(task.task_id, TaskStatus.FAILED, "recovery")
            current = self.repository.get_task(task.task_id)
            if current is not None and current.status is TaskStatus.FAILED:
                self.tasks.retry(task.task_id, "recovery", self.settings.max_retries)
                recovered = self.repository.get_task(task.task_id)
                self.audit.record(
                    "TASK_RECOVERED_FOR_RETRY",
                    project_id=project_id,
                    actor_id="orchestrator",
                    task_id=task.task_id,
                    payload={"retry_count": recovered.retry_count if recovered is not None else None},
                )

    def request_integration(self, project_id: str) -> str:
        project = self.repository.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        branches = ["frontend", "backend", "testing"]
        for branch in branches:
            self.integration.validate_branch(self.settings.workspaces_dir / project_id / branch)
        approval = self.approvals.request(project_id, "merge_to_main", {"branches": branches})
        self.recovery.checkpoint(project_id, "INTEGRATION_REVIEW", {"approval_id": approval.approval_id})
        return approval.approval_id

    def integrate(self, project_id: str) -> list[str]:
        project = self.repository.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        commits = [
            self.integration.merge_after_approval(
                project_id, Path(project.root_path), branch
            )
            for branch in ("frontend", "backend", "testing")
        ]
        project.status = ProjectStatus.QA
        project.updated_at = datetime.now(UTC)
        self.repository.update_project(project)
        self.recovery.checkpoint(project_id, "INTEGRATED", {"commits": commits})
        return commits

    def run_final_qa(self, project_id: str) -> TestReport:
        project = self.repository.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        report = self.qa.run_final_suite(Path(project.root_path))
        self.repository.save_artifact(new_id("ARTIFACT"), project_id, "qa-report",
                                      project.root_path,
                                      report.model_dump(mode="json"))
        project.status = ProjectStatus.QA if report.status == "PASS" else ProjectStatus.FAILED
        project.updated_at = datetime.now(UTC)
        self.repository.update_project(project)
        self.recovery.checkpoint(project_id, "QA_COMPLETE", {"status": report.status})
        return report

    def create_repair_task(self, bug: BugReport) -> Task:
        return self.qa.create_repair_task(bug)

    def run_browser_qa(
        self, project_id: str, start_command: list[str], readiness_url: str = "http://127.0.0.1:8000/"
    ) -> PlaywrightReport:
        project = self.repository.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        report = self.qa.run_browser_suite(
            PlaywrightRunner(self.settings), project_id, Path(project.root_path), start_command, readiness_url
        )
        self.repository.save_artifact(
            new_id("ARTIFACT"), project_id, "playwright-report",
            str(self.settings.data_dir / "artifacts" / project_id / "qa-report.json"),
            report.model_dump(mode="json"),
        )
        self.recovery.checkpoint(project_id, "PLAYWRIGHT_QA_COMPLETE", {"status": report.status})
        return report

    def deliver(self, project_id: str) -> Path:
        project = self.repository.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        if project.status is not ProjectStatus.QA:
            raise PermissionError("delivery requires a passing QA state")
        plan_entries = [entry for entry in self.repository.list_memory(project_id, "approved-plan") if entry.approved]
        if not plan_entries:
            raise RuntimeError("approved plan is unavailable")
        plan = Plan.model_validate(plan_entries[-1].content)
        qa_reports = [TestReport.model_validate(item["payload"])
                      for item in self.repository.list_artifacts(project_id, "qa-report")]
        report = FinalReport(
            project_id=project_id,
            summary=project.requirement,
            delivered_features=plan.functional_requirements,
            architecture_summary=plan.architecture.summary,
            source_refs=[project.root_path, str(self.settings.workspaces_dir / project_id)],
            build_instructions=["Review the generated source in the project repository.",
                                "Run the documented application commands for the approved stack."],
            test_reports=qa_reports,
            known_issues=[] if all(item.status == "PASS" for item in qa_reports) else ["QA did not pass"],
            security_checks=["Python path ownership and symlink checks", "Docker network disabled by default",
                             "Git worktree isolation", "Pydantic boundary validation"],
            outstanding_approvals=[],
            model_usage={"prompt_tokens": self.repository.usage_totals(project_id)[0],
                         "completion_tokens": self.repository.usage_totals(project_id)[1]},
        )
        path = self.delivery.publish(report)
        project.status = ProjectStatus.COMPLETED
        project.updated_at = datetime.now(UTC)
        self.repository.update_project(project)
        self.recovery.checkpoint(project_id, "DELIVERY_GENERATED", {"path": str(path)})
        return path

    async def _execute_task(self, task: Task) -> None:
        self.tasks.transition(task.task_id, TaskStatus.ASSIGNED, "orchestrator")
        self.tasks.transition(task.task_id, TaskStatus.IN_PROGRESS, "orchestrator")
        agent = next(
            (
                item
                for item in self.repository.list_agents(task.project_id)
                if item.agent_id == task.assigned_agent or item.role == task.assigned_agent
            ),
            None,
        )
        if agent is None:
            raise RuntimeError(f"agent not found for task {task.task_id}")
        execution = TaskExecution(
            task_id=task.task_id,
            project_id=task.project_id,
            attempt_number=task.retry_count + 1,
            agent_id=agent.agent_id,
        )
        self.repository.save_execution(execution)
        runtime = self.runtime
        if runtime is None:
            raise RuntimeError("an Azure OpenAI client is required for development")
        try:
            workspace = self.settings.workspaces_dir / task.project_id / agent.role
            system_prompt = PRIMARY_DEFINITIONS.get(
                agent.role, PRIMARY_DEFINITIONS["testing"]
            ).system_prompt
            proposer = getattr(runtime.client, "propose_tools", None)
            if proposer is not None:
                system_prompt += (
                    " Use the available function tools to do the work in the assigned worktree. "
                    "Worktrees start empty and are scoped to your owned directory. If a list or read "
                    "operation reports a missing path, do not repeat it; create the required file directly "
                    "with create_file, which creates parent directories. Do not inspect '.' or another "
                    "agent's directory. "
                    "Inspect files when needed, create or modify only authorized files, run relevant "
                    "checks, and finish with commit_changes covering every changed path. "
                    "Do not claim completion unless the tool calls actually perform and commit the work."
                )
                committed = False
                written_paths: set[str] = set()
                feedback: list[dict[str, object]] = []
                existing_paths = set(GitWorktreeManager(workspace).changed_paths())
                if existing_paths:
                    recovery_commit = ToolRequest(
                        tool_name="commit_changes",
                        arguments={
                            "paths": sorted(existing_paths),
                            "message": f"Finalize {task.title}",
                        },
                        idempotency_key=f"{task.task_id}-{task.retry_count}-recovery-finalize",
                    )
                    recovery_result = self.tool_gateway.execute(
                        recovery_commit, agent=agent, task=task, workspace=workspace
                    )
                    if recovery_result.status == "SUCCEEDED" and recovery_result.result.get("commit"):
                        committed = True
                for round_number in range(1, 7):
                    if committed:
                        break
                    round_prompt = system_prompt
                    if round_number >= 2 and not written_paths:
                        round_prompt += (
                            " You have already inspected the worktree. For this round, your next "
                            "function call MUST create or modify the required implementation file; "
                            "do not call read_file, list_directory, or git_diff again."
                        )
                    proposals, _ = await runtime.propose_tools(
                        agent=agent,
                        task=task,
                        system_prompt=round_prompt,
                        tools=tool_definitions(agent.allowed_tools),
                        context_note=json.dumps(feedback, separators=(",", ":"))
                        if feedback else "",
                    )
                    if not proposals:
                        break
                    for index, proposal in enumerate(proposals):
                        request = ToolRequest(
                            tool_name=proposal.name,
                            arguments=proposal.arguments,
                            idempotency_key=(
                                f"{task.task_id}-{task.retry_count}-{round_number}-{index}-{proposal.name}"
                            ),
                        )
                        tool_result = self.tool_gateway.execute(
                            request, agent=agent, task=task, workspace=workspace
                        )
                        feedback.append(
                            {
                                "tool": proposal.name,
                                "status": tool_result.status,
                                "result": tool_result.result,
                                "error": tool_result.error,
                            }
                        )
                        if tool_result.status == "SUCCEEDED":
                            if proposal.name in {"create_file", "modify_file"}:
                                path = proposal.arguments.get("path")
                                if isinstance(path, str):
                                    written_paths.add(path)
                            if proposal.name == "commit_changes" and tool_result.result.get("commit"):
                                committed = True
                        elif tool_result.status == "REJECTED":
                            raise RuntimeError(tool_result.error or "tool request rejected")
                    if committed:
                        break
                if not committed and written_paths:
                    candidate_paths = written_paths
                elif not committed:
                    candidate_paths = set(GitWorktreeManager(workspace).changed_paths())
                else:
                    candidate_paths = set()
                if not committed and candidate_paths:
                    finalize = ToolRequest(
                        tool_name="commit_changes",
                        arguments={
                            "paths": sorted(candidate_paths),
                            "message": f"Implement {task.title}",
                        },
                        idempotency_key=f"{task.task_id}-{task.retry_count}-orchestrator-finalize",
                    )
                    finalize_result = self.tool_gateway.execute(
                        finalize, agent=agent, task=task, workspace=workspace
                    )
                    if finalize_result.status == "SUCCEEDED" and finalize_result.result.get("commit"):
                        committed = True
                if not committed:
                    raise RuntimeError("agent did not commit any implemented changes")
            else:
                result = await runtime.invoke(
                    agent=agent,
                    task=task,
                    system_prompt=system_prompt,
                    output_model=AgentWorkResult,
                )
                for raw_request in result.requested_tools:
                    request = ToolRequest.model_validate(raw_request)
                    tool_result = self.tool_gateway.execute(
                        request, agent=agent, task=task, workspace=workspace
                    )
                    if tool_result.status != "SUCCEEDED":
                        raise RuntimeError(tool_result.error or "tool request failed")
                if not result.completed:
                    raise RuntimeError("agent did not report completed work")
            self.tasks.transition(task.task_id, TaskStatus.REVIEW, "orchestrator")
            self.tasks.transition(task.task_id, TaskStatus.COMPLETED, "orchestrator")
            execution.status = "COMPLETED"
        except Exception as error:
            execution.status = "FAILED"
            execution.error_classification = type(error).__name__
            self.tasks.transition(task.task_id, TaskStatus.FAILED, "orchestrator")
            raise
        finally:
            execution.ended_at = datetime.now(UTC)
            self.repository.save_execution(execution)

    def recover(self, project_id: str) -> tuple[str, dict[str, object]] | None:
        return self.recovery.recover(project_id)
