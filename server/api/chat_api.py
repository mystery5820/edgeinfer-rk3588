from __future__ import annotations

import os
import time
import uuid
from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from server.model_manager.registry import ModelRegistry
from server.runtime.rkllm_backend import RKLLMBackend
from server.scheduler.request_queue import (
    LLMQueueBusyError,
    LLMQueueTimeoutError,
    llm_queue,
)

router = APIRouter(prefix="/v1", tags=["chat"])

LLM_TIMEOUT_SECONDS = float(os.environ.get("EDGEINFER_LLM_TIMEOUT_SECONDS", "90"))


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = Field(default="qwen3-4b-rkllm-all-npu")
    messages: List[ChatMessage]
    max_new_tokens: int = Field(default=128, ge=1, le=256)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    stream: bool = False


def render_prompt(messages: List[ChatMessage]) -> str:
    lines = []
    for msg in messages:
        if msg.role == "system":
            lines.append(f"System: {msg.content}")
        elif msg.role == "user":
            lines.append(f"User: {msg.content}")
        elif msg.role == "assistant":
            lines.append(f"Assistant: {msg.content}")
    lines.append("Assistant:")
    return "\n".join(lines)


def _error_detail(
    *,
    code: str,
    message: str,
    model_id: Optional[str] = None,
    retryable: bool = False,
):
    return {
        "error": {
            "code": code,
            "message": message,
            "type": "edgeinfer_error",
            "retryable": retryable,
        },
        "edgeinfer": {
            "model": model_id,
            "backend": "rkllm-runner",
            "llm": llm_queue.snapshot(),
        },
    }


@router.post("/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    if req.stream:
        raise HTTPException(
            status_code=400,
            detail=_error_detail(
                code="stream_not_supported",
                message="stream=true is not supported in Phase 9 MVP",
                model_id=req.model,
                retryable=False,
            ),
        )

    registry = ModelRegistry()

    try:
        model = registry.get_model(req.model or "qwen3-4b-rkllm-all-npu")
    except KeyError as e:
        raise HTTPException(
            status_code=404,
            detail=_error_detail(
                code="model_not_found",
                message=str(e),
                model_id=req.model,
                retryable=False,
            ),
        )

    model_id = model.get("id")

    if model.get("task") != "llm":
        raise HTTPException(
            status_code=400,
            detail=_error_detail(
                code="model_not_llm",
                message=f"model is not an llm model: {model_id}",
                model_id=model_id,
                retryable=False,
            ),
        )

    prompt = render_prompt(req.messages)
    backend = RKLLMBackend()

    try:
        result = await llm_queue.run_nowait(
            lambda: backend.generate(
                prompt=prompt,
                model=model,
                max_new_tokens=req.max_new_tokens,
                timeout_seconds=LLM_TIMEOUT_SECONDS,
            ),
            timeout_seconds=LLM_TIMEOUT_SECONDS + 10,
            model_id=model_id,
        )
    except LLMQueueBusyError as e:
        raise HTTPException(
            status_code=429,
            detail=_error_detail(
                code="llm_backend_busy",
                message=str(e),
                model_id=model_id,
                retryable=True,
            ),
        )
    except LLMQueueTimeoutError as e:
        raise HTTPException(
            status_code=504,
            detail=_error_detail(
                code="llm_timeout",
                message=str(e),
                model_id=model_id,
                retryable=True,
            ),
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=502,
            detail=_error_detail(
                code="rkllm_runtime_error",
                message=str(e),
                model_id=model_id,
                retryable=False,
            ),
        )

    created = int(time.time())

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": created,
        "model": model_id,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result["text"],
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
        },
        "edgeinfer": {
            "backend": result.get("backend"),
            "latency_ms": result.get("latency_ms"),
            "recommended_model": model.get("recommended"),
            "runtime": model.get("runtime"),
            "rknpu_driver": model.get("rknpu_driver"),
            "requirement": model.get("requirement"),
            "llm": llm_queue.snapshot(),
        },
    }
