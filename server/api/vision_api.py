from __future__ import annotations

import os
import time
import uuid
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from server.model_manager.registry import ModelRegistry
from server.runtime.fake_vision_backend import FakeVisionBackend
from server.runtime.rknn_yolo_backend import (
    RKNNYoloDetectProbeBackend,
    RKNNYoloDryBackend,
    RKNNYoloInferenceProbeBackend,
    RKNNYoloProbeError,
)
from server.vision.image_probe import ImageProbeError

router = APIRouter(prefix="/v1", tags=["vision"])


class VisionDetectRequest(BaseModel):
    model: Optional[str] = Field(default=None)
    image_path: Optional[str] = Field(default=None)
    confidence_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    iou_threshold: float = Field(default=0.45, ge=0.0, le=1.0)


def _vision_backend_mode() -> str:
    return os.environ.get("EDGEINFER_VISION_BACKEND_MODE", "fake").strip().lower()


def _vision_backend_name() -> str:
    mode = _vision_backend_mode()
    if mode in {"rknn-detect", "rknn-yolo-detect", "rknn-yolo-detect-probe", "rknn-yolo-postprocess"}:
        return "rknn-yolo-detect-probe"
    if mode in {"rknn-inference", "rknn-yolo-inference", "rknn-yolo-inference-probe", "rknn-yolo-probe"}:
        return "rknn-yolo-inference-probe"
    if mode in {"rknn", "rknn-yolo", "rknn-dryrun", "rknn-yolo-dryrun"}:
        return "rknn-yolo-dryrun"
    return "fake-vision"


def _vision_runtime_name() -> str:
    backend_name = _vision_backend_name()
    if backend_name == "rknn-yolo-detect-probe":
        return "phase18f-yolo-postprocess-integration"
    if backend_name == "rknn-yolo-inference-probe":
        return "phase18e-rknn-yolo-inference-probe"
    if backend_name == "rknn-yolo-dryrun":
        return "phase18d-rknn-yolo-dryrun"
    return "phase18c-image-input-skeleton"


def _vision_metrics_snapshot() -> Dict[str, object]:
    backend_name = _vision_backend_name()
    if backend_name == "rknn-yolo-detect-probe":
        return RKNNYoloDetectProbeBackend.metrics_snapshot()
    if backend_name == "rknn-yolo-inference-probe":
        return RKNNYoloInferenceProbeBackend.metrics_snapshot()
    if backend_name == "rknn-yolo-dryrun":
        return RKNNYoloDryBackend.metrics_snapshot()
    return FakeVisionBackend.metrics_snapshot()


def _vision_error_detail(
    *,
    code: str,
    message: str,
    model_id: Optional[str] = None,
    retryable: bool = False,
) -> Dict[str, object]:
    return {
        "error": {
            "code": code,
            "message": message,
            "type": "edgeinfer_error",
            "retryable": retryable,
        },
        "edgeinfer": {
            "model": model_id,
            "backend": _vision_backend_name(),
            "runtime": _vision_runtime_name(),
            "vision": _vision_metrics_snapshot(),
        },
    }


def _resolve_vision_model(registry: ModelRegistry, model_id: Optional[str]) -> Dict[str, object]:
    if model_id:
        try:
            model = registry.get_model(model_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail=_vision_error_detail(
                    code="model_not_found",
                    message=str(exc),
                    model_id=model_id,
                    retryable=False,
                ),
            ) from exc
    else:
        model = registry.get_default_model("object-detection")
        if not model:
            raise HTTPException(
                status_code=404,
                detail=_vision_error_detail(
                    code="vision_model_not_configured",
                    message="no object-detection model is configured",
                    model_id=None,
                    retryable=False,
                ),
            )

    if model.get("task") != "object-detection":
        resolved_id = str(model.get("id", model_id or ""))
        raise HTTPException(
            status_code=400,
            detail=_vision_error_detail(
                code="model_not_vision",
                message=f"model is not an object-detection model: {resolved_id}",
                model_id=resolved_id,
                retryable=False,
            ),
        )

    return model


def _run_backend(
    *,
    model: Dict[str, object],
    image_path: str,
    confidence_threshold: float,
    iou_threshold: float,
) -> Dict[str, object]:
    backend_name = _vision_backend_name()
    if backend_name == "rknn-yolo-detect-probe":
        return RKNNYoloDetectProbeBackend.detect(
            model=model,
            image_path=image_path,
            confidence_threshold=confidence_threshold,
            iou_threshold=iou_threshold,
        )

    if backend_name == "rknn-yolo-inference-probe":
        return RKNNYoloInferenceProbeBackend.detect(
            model=model,
            image_path=image_path,
            confidence_threshold=confidence_threshold,
            iou_threshold=iou_threshold,
        )

    if backend_name == "rknn-yolo-dryrun":
        return RKNNYoloDryBackend.detect(
            model=model,
            image_path=image_path,
            confidence_threshold=confidence_threshold,
            iou_threshold=iou_threshold,
        )

    return FakeVisionBackend.detect(
        model=model,
        image_path=image_path,
        confidence_threshold=confidence_threshold,
        iou_threshold=iou_threshold,
    )


@router.post("/vision/detect")
def vision_detect(req: VisionDetectRequest):
    registry = ModelRegistry()
    model = _resolve_vision_model(registry, req.model)

    if req.image_path is None or not req.image_path.strip():
        raise HTTPException(
            status_code=400,
            detail=_vision_error_detail(
                code="invalid_image_path",
                message="image_path must be a non-empty string",
                model_id=str(model.get("id")),
                retryable=False,
            ),
        )

    image_path = req.image_path.strip()
    started = time.time()

    try:
        result = _run_backend(
            model=model,
            image_path=image_path,
            confidence_threshold=req.confidence_threshold,
            iou_threshold=req.iou_threshold,
        )
    except FileNotFoundError as exc:
        message = str(exc)
        code = "image_not_found"
        if "RKNN model not found" in message:
            code = "vision_model_file_not_found"
        raise HTTPException(
            status_code=404,
            detail=_vision_error_detail(
                code=code,
                message=message,
                model_id=str(model.get("id")),
                retryable=False,
            ),
        ) from exc
    except ImageProbeError as exc:
        raise HTTPException(
            status_code=400,
            detail=_vision_error_detail(
                code="invalid_image_file",
                message=str(exc),
                model_id=str(model.get("id")),
                retryable=False,
            ),
        ) from exc
    except RKNNYoloProbeError as exc:
        raise HTTPException(
            status_code=500,
            detail=_vision_error_detail(
                code="rknn_yolo_runtime_error",
                message=str(exc),
                model_id=str(model.get("id")),
                retryable=True,
            ),
        ) from exc

    total_ms = (time.time() - started) * 1000.0
    latency_ms = dict(result["latency_ms"])
    latency_ms["total"] = round(total_ms, 3)

    return {
        "id": f"visiondet-{uuid.uuid4().hex[:12]}",
        "object": "vision.detection",
        "created": int(time.time()),
        "model": model.get("id"),
        "image": result["image"],
        "objects": result["objects"],
        "latency_ms": latency_ms,
        "edgeinfer": {
            "backend": _vision_backend_name(),
            "runtime": _vision_runtime_name(),
            "image_path": image_path,
            "thresholds": {
                "confidence": req.confidence_threshold,
                "iou": req.iou_threshold,
            },
            "model_runtime": result.get("model_runtime"),
            "note": "Phase 18F can run RKNNLite inference and YOLO postprocess to return detection objects. This remains an opt-in probe backend.",
            "vision": _vision_metrics_snapshot(),
        },
    }
