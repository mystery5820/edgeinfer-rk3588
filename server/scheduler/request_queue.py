from __future__ import annotations

import asyncio
from typing import Awaitable, TypeVar

T = TypeVar("T")


class LLMRequestQueue:
    def __init__(self, max_concurrent: int = 1):
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def run(self, task: Awaitable[T], timeout_seconds: float) -> T:
        async with self._semaphore:
            return await asyncio.wait_for(task, timeout=timeout_seconds)


llm_queue = LLMRequestQueue(max_concurrent=1)
