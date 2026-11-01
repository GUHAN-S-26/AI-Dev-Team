"""Task creation, dependency validation, and state transitions."""

from __future__ import annotations

from datetime import UTC, datetime

from app.database.repository import Repository
from app.schemas.models import PlanTask, Task, TaskStatus
from app.security.audit_logger import AuditLogger
from app.tasks.state_machine import InvalidTaskTransition, validate_transition


class TaskManager:
    def __init__(self, repository: Repository, audit: AuditLogger) -> None:
        self.repository = repository
        self.audit = audit

    def create_tasks(self, project_id: str, plan_tasks: list[PlanTask]) -> list[Task]:
        ids = {task.task_id for task in plan_tasks}
        if len(ids) != len(plan_tasks):
            raise ValueError("task IDs must be unique")
        existing = {task.task_id for task in self.repository.list_tasks(project_id)}
        duplicate = ids & existing
        if duplicate:
            raise ValueError(f"task IDs already exist: {', '.join(sorted(duplicate))}")
        for plan_task in plan_tasks:
            if any(dependency not in ids for dependency in plan_task.dependencies):
                raise ValueError(f"task {plan_task.task_id} has an unknown dependency")
        self._assert_acyclic(plan_tasks)
        tasks: list[Task] = [Task(project_id=project_id, **task.model_dump()) for task in plan_tasks]
        for persisted_task in tasks:
            self.repository.save_task(persisted_task)
            self.audit.record(
                "TASK_CREATED",
                project_id=project_id,
                actor_id="orchestrator",
                task_id=persisted_task.task_id,
                payload=persisted_task.model_dump(mode="json"),
            )
        return tasks

    def transition(self, task_id: str, target: TaskStatus, actor_id: str) -> Task:
        task = self.repository.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        validate_transition(task.status, target)
        previous_status = task.status
        if target is TaskStatus.IN_PROGRESS:
            for dependency_id in task.dependencies:
                dependency = self.repository.get_task(dependency_id)
                if dependency is None or dependency.status is not TaskStatus.COMPLETED:
                    raise InvalidTaskTransition(f"dependency {dependency_id} is not completed")
        task.status = target
        task.updated_at = datetime.now(UTC)
        self.repository.save_task(task)
        self.audit.record(
            "TASK_TRANSITION",
            project_id=task.project_id,
            actor_id=actor_id,
            task_id=task_id,
            payload={"from": previous_status.value, "to": target.value},
        )
        return task

    def retry(self, task_id: str, actor_id: str, max_retries: int) -> Task:
        task = self.repository.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        if task.status is not TaskStatus.FAILED:
            raise InvalidTaskTransition("only failed tasks can be retried")
        if task.retry_count >= max_retries:
            raise InvalidTaskTransition("task retry limit exhausted")
        task.retry_count += 1
        return self.transition(task_id, TaskStatus.PENDING, actor_id)

    def eligible(self, project_id: str) -> list[Task]:
        tasks = self.repository.list_tasks(project_id)
        by_id = {task.task_id: task for task in tasks}
        eligible = [
            task
            for task in tasks
            if task.status is TaskStatus.PENDING
            and all(
                by_id[dependency].status is TaskStatus.COMPLETED for dependency in task.dependencies
            )
        ]
        return sorted(eligible, key=lambda task: (-self._priority(task), task.task_id))

    @staticmethod
    def _priority(task: Task) -> int:
        return {"critical": 4, "high": 3, "medium": 2, "low": 1}[task.priority.value]

    @staticmethod
    def _assert_acyclic(tasks: list[PlanTask]) -> None:
        graph = {task.task_id: task.dependencies for task in tasks}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise ValueError("task dependency cycle detected")
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph[node]:
                visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for node in graph:
            visit(node)
