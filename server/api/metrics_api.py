from __future__ import annotations

import os
import resource
import time

from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["metrics"])

START_TIME = time.time()


@router.get("/metrics")
def metrics():
    usage = resource.getrusage(resource.RUSAGE_SELF)

    return {
        "uptime_seconds": round(time.time() - START_TIME, 3),
        "pid": os.getpid(),
        "process_max_rss_kb": usage.ru_maxrss,
        "llm": {
            "max_concurrent": 1,
            "queue_enabled": True,
        },
        "notes": "Phase 9 MVP metrics. NPU / RKLLM runtime metrics will be added after backend wrapper is fixed.",
    }
