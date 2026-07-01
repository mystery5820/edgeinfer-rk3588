from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, Dict, Optional, TypeVar

T = TypeVar("T")


class LLMQueueBusyError(RuntimeError):
    pass


class LLMQueueTimeoutError(RuntimeError):
    pass


class LLMRequestQueue:
    def __init__(self, max_concurrent: int = 1):
        if max_concurrent != 1:
            raise ValueError("Phase 9 MVP only supports max_concurrent=1 for RKLLM")

        self.max_concurrent = max_concurrent
        self._lock = asyncio.Lock()

        self.total_requests = 0
        self.accepted_requests = 0
        self.rejected_busy = 0
        self.completed_requests = 0
        self.failed_requests = 0
        self.timeout_requests = 0

        self.last_error: Optional[str] = None
        self.last_latency_ms: Optional[float] = None
        self.last_started_at: Optional[float] = None
        self.last_finished_at: Optional[float] = None
        self.current_model: Optional[str] = None

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    async def run_nowait(
        self,
        task_factory: Callable[[], Awaitable[T]],
        *,
        timeout_seconds: float,
        model_id: Optional[str] = None,
    ) -> T:
        """
        Run one LLM task if the backend is idle.

        If another LLM request is already running, reject immediately instead
        of waiting in a queue. This avoids multiple Qwen3/RKLLM processes
        competing for RKNPU/DRM/IOVA resources.
        """
        self.total_requests += 1

        if self._lock.locked():
            self.rejected_busy += 1
            self.last_error = "LLM backend busy"
            raise LLMQueueBusyError("LLM backend is busy; please retry later")

        async with self._lock:
            self.accepted_requests += 1
            self.current_model = model_id
            self.last_started_at = time.time()
            self.last_finished_at = None
            start = time.time()

            try:
                result = await asyncio.wait_for(
                    task_factory(),
                    timeout=timeout_seconds,
                )
            except asyncio.TimeoutError as e:
                self.timeout_requests += 1
                self.failed_requests += 1
                self.last_error = f"LLM request timeout after {timeout_seconds}s"
                raise LLMQueueTimeoutError(self.last_error) from e
            except Exception as e:
                self.failed_requests += 1
                self.last_error = str(e)
                raise
            else:
                self.completed_requests += 1
                self.last_error = None
                return result
            finally:
                self.last_latency_ms = round((time.time() - start) * 1000, 3)
                self.last_finished_at = time.time()
                self.current_model = None

    def snapshot(self) -> Dict[str, object]:
        return {
            "max_concurrent": self.max_concurrent,
            "busy": self.busy,
            "queue_policy": "reject_when_busy",
            "total_requests": self.total_requests,
            "accepted_requests": self.accepted_requests,
            "rejected_busy": self.rejected_busy,
            "completed_requests": self.completed_requests,
            "failed_requests": self.failed_requests,
            "timeout_requests": self.timeout_requests,
            "last_error": self.last_error,
            "last_latency_ms": self.last_latency_ms,
            "last_started_at": self.last_started_at,
            "last_finished_at": self.last_finished_at,
            "current_model": self.current_model,
        }


llm_queue = LLMRequestQueue(max_concurrent=1)
