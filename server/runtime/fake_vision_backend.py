from __future__ import annotations

import time
from typing import Dict, List


class FakeVisionBackend:
    """Minimal vision backend used to freeze the /v1/vision/detect contract.

    Phase 18B intentionally does not call RKNN runtime yet. This backend returns
    an empty detection list with stable latency fields so API clients, tests and
    documentation can be developed before real YOLO RKNN integration.
    """

    _total_requests = 0
    _completed_requests = 0
    _failed_requests = 0
    _last_latency_ms = None
    _last_error = None
    _last_started_at = None
    _last_finished_at = None
    _current_model = None

    @classmethod
    def metrics_snapshot(cls) -> Dict[str, object]:
        return {
            "total_requests": cls._total_requests,
            "completed_requests": cls._completed_requests,
            "failed_requests": cls._failed_requests,
            "last_error": cls._last_error,
            "last_latency_ms": cls._last_latency_ms,
            "last_started_at": cls._last_started_at,
            "last_finished_at": cls._last_finished_at,
            "current_model": cls._current_model,
        }

    @classmethod
    def detect(
        cls,
        *,
        model: Dict[str, object],
        image_path: str,
        confidence_threshold: float,
        iou_threshold: float,
    ) -> Dict[str, object]:
        cls._total_requests += 1
        cls._last_started_at = time.time()
        cls._current_model = model.get("id")

        started = time.time()
        try:
            # Keep the skeleton deterministic. The numbers are placeholders for
            # the final response schema, not real model timings.
            latency_ms = {
                "preprocess": 0.0,
                "inference": 0.0,
                "postprocess": 0.0,
            }
            objects: List[Dict[str, object]] = []

            elapsed_ms = (time.time() - started) * 1000.0
            cls._completed_requests += 1
            cls._last_latency_ms = round(elapsed_ms, 3)
            cls._last_error = None
            cls._last_finished_at = time.time()
            cls._current_model = None

            return {
                "objects": objects,
                "latency_ms": latency_ms,
            }
        except Exception as exc:
            cls._failed_requests += 1
            cls._last_error = repr(exc)
            cls._last_finished_at = time.time()
            cls._current_model = None
            raise
