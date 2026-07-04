from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, Dict, Optional, TypeVar

T = TypeVar("T")


class LLMQueueBusyError(RuntimeError):
    pass


class LLMQueueTimeoutError(RuntimeError):
    pass


class LLMRequestLease:
    def __init__(self, queue: "LLMRequestQueue", *, start: float):
        self._queue = queue
        self._start = start
        self._released = False

    @property
    def released(self) -> bool:
        return self._released

    def finish_success(self) -> None:
        self._queue._finish_lease(self, error=None)

    def finish_error(self, error: BaseException | str) -> None:
        self._queue._finish_lease(self, error=error)


class LLMRequestQueue:
    def __init__(self, max_concurrent: int = 1):
        if max_concurrent != 1:
            raise ValueError("Phase 10 MVP only supports max_concurrent=1 for RKLLM")

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

    async def acquire_nowait(
        self,
        *,
        model_id: Optional[str] = None,
    ) -> LLMRequestLease:
        self.total_requests += 1

        if self._lock.locked():
            self.rejected_busy += 1
            self.last_error = "LLM backend busy"
            raise LLMQueueBusyError("LLM backend is busy; please retry later")

        await self._lock.acquire()

        self.accepted_requests += 1
        self.current_model = model_id
        self.last_started_at = time.time()
        self.last_finished_at = None
        self.last_error = None

        return LLMRequestLease(self, start=time.time())

    def _finish_lease(
        self,
        lease: LLMRequestLease,
        *,
        error: BaseException | str | None,
    ) -> None:
        if lease.released:
            return

        lease._released = True

        if error is None:
            self.completed_requests += 1
            self.last_error = None
        else:
            self.failed_requests += 1
            self.last_error = str(error)

        self.last_latency_ms = round((time.time() - lease._start) * 1000, 3)
        self.last_finished_at = time.time()
        self.current_model = None

        if self._lock.locked():
            self._lock.release()

    async def run_nowait(
        self,
        task_factory: Callable[[], Awaitable[T]],
        *,
        timeout_seconds: float,
        model_id: Optional[str] = None,
    ) -> T:
        lease = await self.acquire_nowait(model_id=model_id)

        try:
            result = await asyncio.wait_for(
                task_factory(),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError as e:
            self.timeout_requests += 1
            lease.finish_error(f"LLM request timeout after {timeout_seconds}s")
            raise LLMQueueTimeoutError(self.last_error or "LLM request timeout") from e
        except Exception as e:
            lease.finish_error(e)
            raise
        else:
            lease.finish_success()
            return result

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
