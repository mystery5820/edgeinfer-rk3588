from __future__ import annotations

import threading
import time
from typing import Dict, Optional


PHASE20_RUNTIME = "phase20-global-npu-resource-guard"


class NPUResourceBusyError(RuntimeError):
    pass


class NPUResourceLease:
    def __init__(
        self,
        guard: "NPUResourceGuard",
        *,
        task: str,
        owner: str,
        model_id: Optional[str],
        start: float,
    ):
        self._guard = guard
        self.task = task
        self.owner = owner
        self.model_id = model_id
        self._start = start
        self._released = False

    @property
    def released(self) -> bool:
        return self._released

    def finish_success(self) -> None:
        self._guard._finish_lease(self, error=None)

    def finish_error(self, error: BaseException | str) -> None:
        self._guard._finish_lease(self, error=error)


class NPUResourceGuard:
    """Global RK3588 NPU resource guard.

    Phase 20 MVP policy:
      - max_concurrent = 1
      - reject_when_busy
      - cross-task protection above LLM/Vision queues
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stats_lock = threading.Lock()

        self.max_concurrent = 1
        self.queue_policy = "reject_when_busy"

        self.total_acquire = 0
        self.accepted_acquire = 0
        self.rejected_busy = 0
        self.completed = 0
        self.failed = 0

        self.current_task: Optional[str] = None
        self.current_model: Optional[str] = None
        self.current_owner: Optional[str] = None

        self.last_error: Optional[str] = None
        self.last_latency_ms: Optional[float] = None
        self.last_started_at: Optional[float] = None
        self.last_finished_at: Optional[float] = None

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    def acquire_nowait(
        self,
        *,
        task: str,
        owner: str,
        model_id: Optional[str] = None,
    ) -> NPUResourceLease:
        with self._stats_lock:
            self.total_acquire += 1

            if self._lock.locked():
                self.rejected_busy += 1
                self.last_error = "NPU resource busy"
                raise NPUResourceBusyError("NPU resource is busy; please retry later")

            acquired = self._lock.acquire(blocking=False)
            if not acquired:
                self.rejected_busy += 1
                self.last_error = "NPU resource busy"
                raise NPUResourceBusyError("NPU resource is busy; please retry later")

            self.accepted_acquire += 1
            self.current_task = task
            self.current_model = model_id
            self.current_owner = owner
            self.last_started_at = time.time()
            self.last_finished_at = None
            self.last_error = None

            return NPUResourceLease(
                self,
                task=task,
                owner=owner,
                model_id=model_id,
                start=time.time(),
            )

    def _finish_lease(
        self,
        lease: NPUResourceLease,
        *,
        error: BaseException | str | None,
    ) -> None:
        if lease.released:
            return

        lease._released = True

        with self._stats_lock:
            if error is None:
                self.completed += 1
                self.last_error = None
            else:
                self.failed += 1
                self.last_error = str(error)

            self.last_latency_ms = round((time.time() - lease._start) * 1000, 3)
            self.last_finished_at = time.time()

            self.current_task = None
            self.current_model = None
            self.current_owner = None

            if self._lock.locked():
                self._lock.release()

    def snapshot(self) -> Dict[str, object]:
        with self._stats_lock:
            return {
                "runtime": PHASE20_RUNTIME,
                "max_concurrent": self.max_concurrent,
                "busy": self.busy,
                "queue_policy": self.queue_policy,
                "total_acquire": self.total_acquire,
                "accepted_acquire": self.accepted_acquire,
                "rejected_busy": self.rejected_busy,
                "completed": self.completed,
                "failed": self.failed,
                "current_task": self.current_task,
                "current_model": self.current_model,
                "current_owner": self.current_owner,
                "last_error": self.last_error,
                "last_latency_ms": self.last_latency_ms,
                "last_started_at": self.last_started_at,
                "last_finished_at": self.last_finished_at,
            }


npu_resource_guard = NPUResourceGuard()


def npu_resource_error_detail(
    *,
    task: str,
    owner: str,
    model_id: Optional[str],
) -> Dict[str, object]:
    return {
        "error": {
            "code": "npu_resource_busy",
            "message": "NPU resource is busy; please retry later",
            "type": "edgeinfer_error",
            "retryable": True,
        },
        "edgeinfer": {
            "task": task,
            "model": model_id,
            "backend": "npu-resource-guard",
            "runtime": PHASE20_RUNTIME,
            "owner": owner,
            "npu_resource": npu_resource_guard.snapshot(),
        },
    }
