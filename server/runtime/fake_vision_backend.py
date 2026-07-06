from __future__ import annotations

import time
from typing import Dict, List, Tuple

from server.vision.image_probe import ImageProbeError, probe_image


class FakeVisionBackend:
    """Vision backend used before real RKNN YOLO integration.

    Phase 18C probes real image metadata using pure Python so the board-side
    serving venv does not need OpenCV, Pillow or NumPy yet.
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

    @staticmethod
    def _target_size(model: Dict[str, object]) -> Tuple[int, int]:
        value = model.get("input_size") or model.get("input_shape") or [640, 640]
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            try:
                return int(value[0]), int(value[1])
            except Exception:
                pass
        return 640, 640

    @staticmethod
    def _build_preprocess_plan(image: Dict[str, object], target_width: int, target_height: int) -> Dict[str, object]:
        width = max(1, int(image["width"]))
        height = max(1, int(image["height"]))
        scale = min(target_width / width, target_height / height)
        resized_width = int(round(width * scale))
        resized_height = int(round(height * scale))
        pad_x = max(0, target_width - resized_width)
        pad_y = max(0, target_height - resized_height)

        return {
            "method": "letterbox-metadata-only",
            "target_width": target_width,
            "target_height": target_height,
            "scale": round(float(scale), 6),
            "resized_width": resized_width,
            "resized_height": resized_height,
            "pad_left": pad_x // 2,
            "pad_right": pad_x - pad_x // 2,
            "pad_top": pad_y // 2,
            "pad_bottom": pad_y - pad_y // 2,
            "note": "No pixel resize is performed in Phase 18C; this is a preprocess metadata skeleton.",
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
            load_started = time.time()
            image = probe_image(image_path)
            load_image_ms = (time.time() - load_started) * 1000.0

            preprocess_started = time.time()
            target_width, target_height = cls._target_size(model)
            preprocess = cls._build_preprocess_plan(image, target_width, target_height)
            preprocess_ms = (time.time() - preprocess_started) * 1000.0

            # Phase 18C does not perform real RKNN inference or YOLO postprocess.
            inference_ms = 0.0
            postprocess_ms = 0.0
            objects: List[Dict[str, object]] = []

            elapsed_ms = (time.time() - started) * 1000.0
            cls._completed_requests += 1
            cls._last_latency_ms = round(elapsed_ms, 3)
            cls._last_error = None
            cls._last_finished_at = time.time()
            cls._current_model = None

            return {
                "objects": objects,
                "image": {
                    "path": image["path"],
                    "format": image["format"],
                    "width": image["width"],
                    "height": image["height"],
                    "channels": image["channels"],
                    "size_bytes": image["size_bytes"],
                    "preprocess": preprocess,
                },
                "latency_ms": {
                    "load_image": round(load_image_ms, 3),
                    "preprocess": round(preprocess_ms, 3),
                    "inference": inference_ms,
                    "postprocess": postprocess_ms,
                },
            }
        except Exception as exc:
            cls._failed_requests += 1
            cls._last_error = repr(exc)
            cls._last_finished_at = time.time()
            cls._current_model = None
            raise
