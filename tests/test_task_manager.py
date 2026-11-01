from app.schemas.models import PlanTask, Priority, TaskStatus
from app.security.audit_logger import AuditLogger
from app.tasks.task_manager import TaskManager


def test_task_transitions_and_dependency_gate(repository):
    from app.schemas.models import Project

    project = Project(
        project_id="PROJECT-test",
        name="test",
        requirement="a valid requirement here",
        root_path="/tmp/project",
    )
    repository.create_project(project)
    manager = TaskManager(repository, AuditLogger(repository))
    first, second = manager.create_tasks(
        project.project_id,
        [
            PlanTask(
                task_id="TASK-a",
                title="a",
                description="a",
                assigned_agent="backend",
                acceptance_criteria=["a"],
            ),
            PlanTask(
                task_id="TASK-b",
                title="b",
                description="b",
                assigned_agent="frontend",
                dependencies=["TASK-a"],
                acceptance_criteria=["b"],
                priority=Priority.HIGH,
            ),
        ],
    )
    manager.transition(first.task_id, TaskStatus.ASSIGNED, "orchestrator")
    manager.transition(first.task_id, TaskStatus.IN_PROGRESS, "orchestrator")
    manager.transition(first.task_id, TaskStatus.REVIEW, "orchestrator")
    manager.transition(first.task_id, TaskStatus.COMPLETED, "orchestrator")
    assert [task.task_id for task in manager.eligible(project.project_id)] == [second.task_id]


def test_task_cycle_is_rejected(repository):
    from app.schemas.models import Project

    project = Project(
        project_id="PROJECT-cycle",
        name="cycle",
        requirement="a valid requirement here",
        root_path="/tmp/project",
    )
    repository.create_project(project)
    manager = TaskManager(repository, AuditLogger(repository))
    try:
        manager.create_tasks(
            project.project_id,
            [
                PlanTask(
                    task_id="TASK-a",
                    title="a",
                    description="a",
                    assigned_agent="backend",
                    dependencies=["TASK-b"],
                    acceptance_criteria=["a"],
                ),
                PlanTask(
                    task_id="TASK-b",
                    title="b",
                    description="b",
                    assigned_agent="frontend",
                    dependencies=["TASK-a"],
                    acceptance_criteria=["b"],
                ),
            ],
        )
    except ValueError as error:
        assert "cycle" in str(error)
    else:
        raise AssertionError("cycle was accepted")
