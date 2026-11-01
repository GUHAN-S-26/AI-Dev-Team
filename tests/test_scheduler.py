import asyncio

import pytest

from app.orchestrator.scheduler import Scheduler
from app.schemas.models import Task


@pytest.mark.asyncio
async def test_scheduler_runs_independent_tasks_concurrently():
    tasks = [
        Task(
            task_id=f"TASK-{index}",
            project_id="PROJECT",
            title=str(index),
            description="x",
            assigned_agent="backend",
            acceptance_criteria=["x"],
        )
        for index in range(3)
    ]
    active = 0
    maximum = 0

    async def handler(task):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0.01)
        active -= 1

    await Scheduler(3).run(tasks, handler)
    assert maximum == 3
