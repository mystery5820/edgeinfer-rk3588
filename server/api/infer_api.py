from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from server.api.vision_api import VisionDetectRequest, vision_detect
from server.runtime.vlm_placeholder_backend import VLMPlaceholderBackend, VLM_TASKS
from server.runtime.qwen3_vl_backend import Qwen3VLBackend, Qwen3VLBackendError
from server.scheduler.npu_resource_guard import NPUResourceBusyError, npu_resource_error_detail
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



def _int_param(task: str, parameters: Dict[str, Any], key: str, default: int) -> int:
    value = parameters.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail=_error_detail(
                code="invalid_parameter",
                message=f"{key} must be an integer",
                task=task,
                backend="qwen3-vl-adapter",
                retryable=False,
                extra={"parameter": key, "value": value},
            ),
        )


def _vlm_prompt_from_request(req: UnifiedInferRequest, task: str) -> str:
    input_data = req.input or {}

    for key in ("prompt", "text", "question"):
        value = input_data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    if task == "image-captioning":
        return "Describe this image in one sentence."

    if task == "visual-question-answering":
        raise HTTPException(
            status_code=400,
            detail=_error_detail(
                code="invalid_vlm_input",
                message="visual-question-answering input.question or input.prompt must be a non-empty string",
                task=task,
                backend="qwen3-vl-adapter",
            ),
        )

    return "Describe this image in one sentence."


def _vlm_image_path_from_request(req: UnifiedInferRequest, task: str) -> str:
    input_data = req.input or {}

    image_path = input_data.get("image_path")
    if isinstance(image_path, str) and image_path.strip():
        return image_path.strip()

    image = input_data.get("image")
    if isinstance(image, dict):
        path = image.get("path")
        if isinstance(path, str) and path.strip():
            return path.strip()

    raise HTTPException(
        status_code=400,
        detail=_error_detail(
            code="invalid_vlm_input",
            message="VLM input.image_path must be a non-empty board-side image path",
            task=task,
            backend="qwen3-vl-adapter",
        ),
    )


def _dispatch_vlm(req: UnifiedInferRequest, task: str) -> Dict[str, Any]:
    parameters = req.parameters or {}
    image_path = _vlm_image_path_from_request(req, task)
    prompt = _vlm_prompt_from_request(req, task)

    backend = Qwen3VLBackend()
    model_id = req.model or req.input.get("model") or backend.default_model_id()

    try:
        raw_output = backend.generate(
            task=task,
            image_path=image_path,
            prompt=prompt,
            model_id=str(model_id),
            max_new_tokens=_int_param(task, parameters, "max_new_tokens", 64),
            context_length=_int_param(task, parameters, "context_length", 1024),
            timeout_seconds=_int_param(task, parameters, "timeout_seconds", 180),
        )
    except NPUResourceBusyError as exc:
        raise HTTPException(
            status_code=429,
            detail=npu_resource_error_detail(
                task=task,
                owner="qwen3-vl",
                model_id=str(model_id),
            ),
        ) from exc
    except Qwen3VLBackendError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=_error_detail(
                code=exc.code,
                message=exc.message,
                task=task,
                backend=Qwen3VLBackend.backend_name(),
                retryable=exc.retryable,
                extra=exc.extra,
            ),
        ) from exc

    answer = str(raw_output.get("answer", ""))
    latency_ms = raw_output.get("latency_ms")

    output = {
        "summary": {
            "type": task,
            "answer": answer,
            "latency_ms": latency_ms,
            "image": raw_output.get("image"),
            "model": raw_output.get("model"),
        },
        "data": {
            "answer": answer,
            "prompt": raw_output.get("prompt"),
            "image": raw_output.get("image"),
        },
        "raw": raw_output,
    }

    return {
        "id": _new_id(),
        "object": "edgeinfer.inference",
        "created": int(time.time()),
        "task": task,
        "model": raw_output.get("model"),
        "output": output,
        "edgeinfer": {
            "task": task,
            "route": "/v1/infer",
            "backend": Qwen3VLBackend.backend_name(),
            "runtime": RUNTIME_NAME,
            "source_endpoint": "/v1/infer",
            "task_adapter": "qwen3-vl",
            "source_runtime": Qwen3VLBackend.runtime_name(),
            "dispatch": {
                "task": task,
                "adapter": "qwen3-vl",
                "source_endpoint": "/v1/infer",
                "backend": Qwen3VLBackend.backend_name(),
                "source_runtime": Qwen3VLBackend.runtime_name(),
            },
            "note": "Phase 22 routes VLM tasks to a real Qwen3-VL RKNN+RKLLM backend on RK3588.",
        },
    }

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
                "status": "adapter",
                "backend": Qwen3VLBackend.backend_name(),
                "source_endpoint": "/v1/infer",
            },
            "image-captioning": {
                "status": "adapter",
                "backend": Qwen3VLBackend.backend_name(),
                "source_endpoint": "/v1/infer",
            },
            "visual-question-answering": {
                "status": "adapter",
                "backend": Qwen3VLBackend.backend_name(),
                "source_endpoint": "/v1/infer",
            },
            "multimodal-chat": {
                "status": "adapter",
                "backend": Qwen3VLBackend.backend_name(),
                "source_endpoint": "/v1/infer",
            },
        },
        "note": "Phase 22 enables real Qwen3-VL RKNN+RKLLM backend for VLM tasks on RK3588.",
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
        return _dispatch_vlm(req, task)

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
