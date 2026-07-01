from __future__ import annotations

import os
import resource
import time

from fastapi import APIRouter

from server.scheduler.request_queue import llm_queue

router = APIRouter(prefix="/v1", tags=["metrics"])

START_TIME = time.time()


@router.get("/metrics")
def metrics():
    usage = resource.getrusage(resource.RUSAGE_SELF)

    return {
        "uptime_seconds": round(time.time() - START_TIME, 3),
        "pid": os.getpid(),
        "process_max_rss_kb": usage.ru_maxrss,
        "llm": llm_queue.snapshot(),
        "notes": (
            "Phase 9 serving metrics. The current RKLLM backend uses a "
            "one-shot subprocess runner and rejects concurrent LLM requests."
        ),
    }
