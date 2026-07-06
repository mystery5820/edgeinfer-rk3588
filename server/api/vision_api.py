from __future__ import annotations

import time
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from server.model_manager.registry import ModelRegistry
from server.runtime.fake_vision_backend import FakeVisionBackend

router = APIRouter(prefix="/v1", tags=["vision"])


class VisionDetectRequest(BaseModel):
    model: Optional[str] = Field(default=None)
    image_path: Optional[str] = Field(default=None)
    confidence_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    iou_threshold: float = Field(default=0.45, ge=0.0, le=1.0)


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
            "backend": "fake-vision",
            "vision": FakeVisionBackend.metrics_snapshot(),
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


@router.post("/vision/detect")
def vision_detect(req: VisionDetectRequest):
    registry = ModelRegistry()
    model = _resolve_vision_model(registry, req.model)

    if req.image_path is None or not req.image_path.strip():
        raise HTTPException(
            status_code=400,
            detail=_vision_error_detail(
                code="invalid_image_path",
                message="image_path must be a non-empty string in Phase 18B skeleton",
                model_id=str(model.get("id")),
                retryable=False,
            ),
        )

    started = time.time()
    result = FakeVisionBackend.detect(
        model=model,
        image_path=req.image_path.strip(),
        confidence_threshold=req.confidence_threshold,
        iou_threshold=req.iou_threshold,
    )
    total_ms = (time.time() - started) * 1000.0

    latency_ms = dict(result["latency_ms"])
    latency_ms["total"] = round(total_ms, 3)

    return {
        "id": f"visiondet-{uuid.uuid4().hex[:12]}",
        "object": "vision.detection",
        "created": int(time.time()),
        "model": model.get("id"),
        "objects": result["objects"],
        "latency_ms": latency_ms,
        "edgeinfer": {
            "backend": "fake-vision",
            "runtime": "phase18b-skeleton",
            "image_path": req.image_path.strip(),
            "thresholds": {
                "confidence": req.confidence_threshold,
                "iou": req.iou_threshold,
            },
            "note": "Phase 18B API skeleton. Real RKNN YOLO backend will be integrated in later phases.",
            "vision": FakeVisionBackend.metrics_snapshot(),
        },
    }
