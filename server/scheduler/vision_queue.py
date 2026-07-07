from __future__ import annotations

import threading
import time
from typing import Callable, Dict, Optional, TypeVar

T = TypeVar("T")


class VisionQueueBusyError(RuntimeError):
    pass


class VisionQueueTimeoutError(RuntimeError):
    pass


class VisionRequestLease:
    def __init__(self, queue: "VisionRequestQueue", *, start: float):
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


class VisionRequestQueue:
    """Single-worker vision request queue with reject_when_busy policy."""

    def __init__(self, max_concurrent: int = 1):
        if max_concurrent != 1:
            raise ValueError("Phase 18I only supports max_concurrent=1 for RKNN vision worker")

        self.max_concurrent = int(max_concurrent)
        self._lock = threading.Lock()
        self._stats_lock = threading.Lock()

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

    def acquire_nowait(self, *, model_id: Optional[str] = None) -> VisionRequestLease:
        with self._stats_lock:
            self.total_requests += 1

            if self._lock.locked():
                self.rejected_busy += 1
                self.last_error = "Vision backend busy"
                raise VisionQueueBusyError("Vision backend is busy; please retry later")

            acquired = self._lock.acquire(blocking=False)
            if not acquired:
                self.rejected_busy += 1
                self.last_error = "Vision backend busy"
                raise VisionQueueBusyError("Vision backend is busy; please retry later")

            self.accepted_requests += 1
            self.current_model = model_id
            self.last_started_at = time.time()
            self.last_finished_at = None
            self.last_error = None

            return VisionRequestLease(self, start=time.time())

    def _finish_lease(
        self,
        lease: VisionRequestLease,
        *,
        error: BaseException | str | None,
    ) -> None:
        if lease.released:
            return

        lease._released = True

        with self._stats_lock:
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

    def run_nowait(
        self,
        task_factory: Callable[[], T],
        *,
        model_id: Optional[str] = None,
    ) -> T:
        lease = self.acquire_nowait(model_id=model_id)

        try:
            result = task_factory()
        except TimeoutError as e:
            with self._stats_lock:
                self.timeout_requests += 1
            lease.finish_error(e)
            raise VisionQueueTimeoutError(str(e) or "Vision request timeout") from e
        except Exception as e:
            lease.finish_error(e)
            raise
        else:
            lease.finish_success()
            return result

    def snapshot(self) -> Dict[str, object]:
        with self._stats_lock:
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


vision_queue = VisionRequestQueue(max_concurrent=1)
