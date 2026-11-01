"""Deterministic dependency-aware async scheduler."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from app.schemas.models import Task


class Scheduler:
    def __init__(self, max_concurrency: int) -> None:
        self.max_concurrency = max_concurrency

    async def run(self, tasks: list[Task], handler: Callable[[Task], Awaitable[None]]) -> None:
        by_id = {task.task_id: task for task in tasks}
        completed: set[str] = {task.task_id for task in tasks if task.status.value == "COMPLETED"}
        pending = {task.task_id for task in tasks if task.task_id not in completed}
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def execute(task: Task) -> None:
            async with semaphore:
                await handler(task)

        while pending:
            ready = sorted(
                (
                    by_id[task_id]
                    for task_id in pending
                    if all(dependency in completed for dependency in by_id[task_id].dependencies)
                ),
                key=lambda task: task.task_id,
            )
            if not ready:
                unresolved = ", ".join(sorted(pending))
                raise RuntimeError(f"scheduler deadlock or unresolved dependencies: {unresolved}")
            await asyncio.gather(*(execute(task) for task in ready))
            completed.update(task.task_id for task in ready)
            pending.difference_update(task.task_id for task in ready)
