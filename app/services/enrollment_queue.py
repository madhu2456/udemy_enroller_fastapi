"""Freshness-biased priority queue for candidate course enrollments."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import time
from typing import Optional

from app.services.course import Course


@dataclass(order=True)
class PrioritizedCourse:
    """Dataclass holding prioritized course item with freshness bias.

    Priority is set to -discovered_at so min-heap pops newer courses first (FM-002).
    """

    priority: float
    discovered_at: float = field(compare=False)
    course: Optional[Course] = field(compare=False, default=None)
    sequence: int = field(default=0)


class EnrollmentPriorityQueue:
    """Freshness-biased priority queue for candidate course enrollments (FM-002)."""

    def __init__(self, maxsize: int = 0) -> None:
        self._queue: asyncio.PriorityQueue[PrioritizedCourse] = asyncio.PriorityQueue(
            maxsize=maxsize
        )
        self._sequence: int = 0

    async def put(
        self, course: Optional[Course], discovered_at: Optional[float] = None
    ) -> None:
        if discovered_at is None:
            discovered_at = time.time()
        self._sequence += 1
        priority = float("inf") if course is None else -discovered_at
        item = PrioritizedCourse(
            priority=priority,
            discovered_at=discovered_at,
            course=course,
            sequence=self._sequence,
        )
        await self._queue.put(item)

    async def get(self) -> PrioritizedCourse:
        return await self._queue.get()

    def empty(self) -> bool:
        return self._queue.empty()

    def qsize(self) -> int:
        return self._queue.qsize()

    def task_done(self) -> None:
        self._queue.task_done()

    async def join(self) -> None:
        await self._queue.join()
