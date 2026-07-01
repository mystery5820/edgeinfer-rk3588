from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["health"])


@router.get("/health")
def health():
    return {
        "status": "ok",
        "service": "edgeinfer-rk3588-serving",
        "phase": "phase9-serving-framework-mvp",
        "legacy_services_should_be_disabled": [
            "qwen-web-chat.service",
            "yolov5-web.service",
        ],
    }
