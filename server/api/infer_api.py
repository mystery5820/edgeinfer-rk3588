from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from server.api.vision_api import VisionDetectRequest, vision_detect
from server.runtime.vlm_placeholder_backend import VLMPlaceholderBackend, VLM_TASKS
from server.runtime.unified_adapters import (
    RUNTIME_NAME as UNIFIED_RUNTIME_NAME,
    build_unified_infer_response,
    make_chat_completion_adapter_result,
    make_object_detection_adapter_result,
    to_plain_dict,
)

router = APIRouter(prefix="/v1", tags=["infer"])

RUNTIME_NAME = UNIFIED_RUNTIME_NAME

TEXT_GENERATION_TASKS = {"text-generation", "chat-completion"}
VISION_TASKS = {"object-detection"}
SUPPORTED_TASKS = TEXT_GENERATION_TASKS | VISION_TASKS | VLM_TASKS


class UnifiedInferRequest(BaseModel):
    task: str = Field(..., description="Task name, for example text-generation, object-detection, or vision-language.")
    model: Optional[str] = Field(default=None, description="Optional model id. If omitted, task-specific default model is used.")
    input: Dict[str, Any] = Field(default_factory=dict, description="Task-specific input payload.")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Task-specific generation/detection parameters.")


def _new_id() -> str:
    return "infer-" + uuid.uuid4().hex[:12]


def _normalize_task(task: str) -> str:
    return str(task or "").strip().lower().replace("_", "-")


def _error_detail(
    *,
    code: str,
    message: str,
    task: Optional[str],
    backend: str,
    retryable: bool = False,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    detail = {
        "error": {
            "code": code,
            "message": message,
            "type": "edgeinfer_error",
            "retryable": retryable,
        },
        "edgeinfer": {
            "task": task,
            "backend": backend,
            "runtime": RUNTIME_NAME,
        },
    }
    if extra:
        detail["edgeinfer"].update(extra)
    return detail


def _success_response(
    *,
    task: str,
    model: Optional[str],
    route: str,
    backend: str,
    output: Any,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    edgeinfer: Dict[str, Any] = {
        "task": task,
        "route": route,
        "backend": backend,
        "runtime": RUNTIME_NAME,
        "source_endpoint": route,
        "note": "Phase 19A adds /v1/infer task dispatch while preserving existing task-specific endpoints.",
    }
    if extra:
        edgeinfer.update(extra)

    return {
        "id": _new_id(),
        "object": "edgeinfer.inference",
        "created": int(time.time()),
        "task": task,
        "model": model,
        "output": output,
        "edgeinfer": edgeinfer,
    }


def _float_param(task: str, parameters: Dict[str, Any], key: str, default: float) -> float:
    value = parameters.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail=_error_detail(
                code="invalid_parameter",
                message=f"{key} must be a number",
                task=task,
                backend="unified-dispatch",
                retryable=False,
                extra={"parameter": key, "value": value},
            ),
        )


def _dispatch_object_detection(req: UnifiedInferRequest, task: str) -> Dict[str, Any]:
    image_path = req.input.get("image_path")
    if not isinstance(image_path, str) or not image_path.strip():
        raise HTTPException(
            status_code=400,
            detail=_error_detail(
                code="invalid_unified_vision_input",
                message="object-detection input.image_path must be a non-empty string",
                task=task,
                backend="vision-adapter",
            ),
        )

    parameters = req.parameters or {}
    vision_req = VisionDetectRequest(
        model=req.model or req.input.get("model"),
        image_path=image_path,
        confidence_threshold=_float_param(task, parameters, "confidence_threshold", 0.25),
        iou_threshold=_float_param(task, parameters, "iou_threshold", 0.45),
    )

    output = vision_detect(vision_req)
    raw_output = to_plain_dict(output)

    return build_unified_infer_response(
        make_object_detection_adapter_result(
            task=task,
            requested_model=req.model,
            raw_output=raw_output,
        )
    )


def _messages_from_input(input_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    messages = input_data.get("messages")
    if isinstance(messages, list) and messages:
        return messages

    text = input_data.get("text", input_data.get("prompt"))
    if isinstance(text, str) and text.strip():
        return [{"role": "user", "content": text}]

    raise HTTPException(
        status_code=400,
        detail=_error_detail(
            code="invalid_unified_text_input",
            message="text-generation input must include messages, text, or prompt",
            task="text-generation",
            backend="llm-adapter",
        ),
    )


def _dispatch_text_generation(req: UnifiedInferRequest, task: str) -> Dict[str, Any]:
    parameters = req.parameters or {}

    if parameters.get("stream") is True or req.input.get("stream") is True:
        raise HTTPException(
            status_code=400,
            detail=_error_detail(
                code="unified_stream_not_supported",
                message="Phase 19A /v1/infer does not wrap streaming responses yet; use /v1/chat/completions for streaming",
                task=task,
                backend="llm-adapter",
            ),
        )

    try:
        from server.api import chat_api as chat_module
    except Exception as exc:
        raise HTTPException(
            status_code=501,
            detail=_error_detail(
                code="llm_unified_adapter_not_ready",
                message=f"chat API module is not available: {exc}",
                task=task,
                backend="llm-adapter",
            ),
        ) from exc

    request_cls = getattr(chat_module, "ChatCompletionRequest", None)
    handler = getattr(chat_module, "chat_completions", None)

    if request_cls is None or handler is None:
        raise HTTPException(
            status_code=501,
            detail=_error_detail(
                code="llm_unified_adapter_not_ready",
                message="chat API request class or handler was not found",
                task=task,
                backend="llm-adapter",
                extra={
                    "expected_request_class": "ChatCompletionRequest",
                    "expected_handler": "chat_completions",
                },
            ),
        )

    payload: Dict[str, Any] = {
        "model": req.model or req.input.get("model"),
        "messages": _messages_from_input(req.input),
        "stream": False,
    }

    for key in ("max_tokens", "temperature", "top_p"):
        if key in parameters:
            payload[key] = parameters[key]

    if "max_new_tokens" in parameters and "max_tokens" not in payload:
        payload["max_tokens"] = parameters["max_new_tokens"]

    try:
        chat_req = request_cls(**payload)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=_error_detail(
                code="invalid_unified_text_payload",
                message=f"failed to build chat completion request: {exc}",
                task=task,
                backend="llm-adapter",
            ),
        ) from exc

    output = handler(chat_req)
    raw_output = to_plain_dict(output)

    return build_unified_infer_response(
        make_chat_completion_adapter_result(
            task=task,
            requested_model=payload.get("model"),
            raw_output=raw_output,
        )
    )


@router.get("/infer/tasks")
def list_unified_infer_tasks() -> Dict[str, Any]:
    return {
        "object": "edgeinfer.infer.tasks",
        "runtime": RUNTIME_NAME,
        "tasks": {
            "text-generation": {
                "status": "adapter",
                "backend": "llm-adapter",
                "source_endpoint": "/v1/chat/completions",
                "aliases": sorted(TEXT_GENERATION_TASKS),
            },
            "object-detection": {
                "status": "adapter",
                "backend": "vision-adapter",
                "source_endpoint": "/v1/vision/detect",
                "aliases": sorted(VISION_TASKS),
            },
            "vision-language": {
                "status": "placeholder",
                "backend": VLMPlaceholderBackend.backend_name(),
                "source_endpoint": None,
            },
            "image-captioning": {
                "status": "placeholder",
                "backend": VLMPlaceholderBackend.backend_name(),
                "source_endpoint": None,
            },
            "visual-question-answering": {
                "status": "placeholder",
                "backend": VLMPlaceholderBackend.backend_name(),
                "source_endpoint": None,
            },
            "multimodal-chat": {
                "status": "placeholder",
                "backend": VLMPlaceholderBackend.backend_name(),
                "source_endpoint": None,
            },
        },
        "note": "VLM tasks are planned first-class tasks and return 501 until a VLM backend is implemented.",
    }


@router.post("/infer")
def unified_infer(req: UnifiedInferRequest) -> Dict[str, Any]:
    task = _normalize_task(req.task)
    if not task:
        raise HTTPException(
            status_code=400,
            detail=_error_detail(
                code="missing_task",
                message="task must be a non-empty string",
                task=task,
                backend="unified-dispatch",
            ),
        )

    if task in VISION_TASKS:
        return _dispatch_object_detection(req, task)

    if task in TEXT_GENERATION_TASKS:
        return _dispatch_text_generation(req, task)

    if task in VLM_TASKS:
        raise HTTPException(
            status_code=501,
            detail=VLMPlaceholderBackend.not_ready_detail(task=task, model=req.model),
        )

    raise HTTPException(
        status_code=400,
        detail=_error_detail(
            code="unsupported_task",
            message=f"unsupported task: {task}",
            task=task,
            backend="unified-dispatch",
            extra={
                "supported_tasks": sorted(SUPPORTED_TASKS),
                "vlm_tasks": sorted(VLM_TASKS),
            },
        ),
    )
