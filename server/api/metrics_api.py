from __future__ import annotations

import os
import resource
import time

from fastapi import APIRouter

from server.runtime.rkllm_backend import RKLLMBackend
from server.scheduler.request_queue import llm_queue
from server.scheduler.vision_queue import vision_queue
from server.scheduler.npu_resource_guard import npu_resource_guard

router = APIRouter(prefix="/v1", tags=["metrics"])

START_TIME = time.time()


def _rkllm_backend_snapshot() -> dict:
    mode = os.environ.get("EDGEINFER_RKLLM_BACKEND_MODE", "oneshot").strip().lower()
    worker_enabled = mode in {"worker", "persistent", "persistent-worker"}

    worker_ctx = int(os.environ.get("EDGEINFER_RKLLM_WORKER_CTX", "1024"))
    worker_max_new = int(os.environ.get("EDGEINFER_RKLLM_WORKER_MAX_NEW", "128"))

    return {
        "mode": mode,
        "worker_enabled": worker_enabled,
        "worker_ctx": worker_ctx,
        "worker_max_new_tokens": worker_max_new,
        "worker_bin": os.environ.get(
            "EDGEINFER_RKLLM_WORKER_BIN",
            "/home/linaro/edgeinfer-rk3588-board/tools/rkllm_enhanced/"
            "rkllm_enhanced_no_template_no_history",
        ),
        "worker_runtime": (
            RKLLMBackend.worker_runtime_snapshot() if worker_enabled else None
        ),
    }


def _metrics_note(backend: dict) -> str:
    if backend["worker_enabled"]:
        return (
            "Phase 9 serving metrics. The current RKLLM backend uses a "
            "persistent no-history worker and rejects concurrent LLM requests."
        )

    return (
        "Phase 9 serving metrics. The current RKLLM backend uses a "
        "one-shot subprocess runner and rejects concurrent LLM requests."
    )


@router.get("/metrics")
def metrics():
    usage = resource.getrusage(resource.RUSAGE_SELF)
    backend = _rkllm_backend_snapshot()

    return {
        "uptime_seconds": round(time.time() - START_TIME, 3),
        "pid": os.getpid(),
        "process_max_rss_kb": usage.ru_maxrss,
        "rkllm_backend": backend,
        "llm": llm_queue.snapshot(),
        "vision": vision_queue.snapshot(),
        "npu_resource": npu_resource_guard.snapshot(),
        "notes": _metrics_note(backend),
    }
