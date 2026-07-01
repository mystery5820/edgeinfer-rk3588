from __future__ import annotations

import time
import uuid
from typing import List, Optional, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from server.model_manager.registry import ModelRegistry
from server.runtime.rkllm_backend import RKLLMBackend
from server.scheduler.request_queue import llm_queue

router = APIRouter(prefix="/v1", tags=["chat"])


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


@router.post("/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    if req.stream:
        raise HTTPException(status_code=400, detail="stream=true is not supported in Phase 9 MVP")

    registry = ModelRegistry()

    try:
        model = registry.get_model(req.model or "qwen3-4b-rkllm-all-npu")
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if model.get("task") != "llm":
        raise HTTPException(status_code=400, detail=f"model is not an llm model: {model.get('id')}")

    prompt = render_prompt(req.messages)
    backend = RKLLMBackend()

    try:
        result = await llm_queue.run(
            backend.generate(
                prompt=prompt,
                model=model,
                max_new_tokens=req.max_new_tokens,
                timeout_seconds=60,
            ),
            timeout_seconds=60,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except TimeoutError:
        raise HTTPException(status_code=504, detail="LLM request timeout")

    created = int(time.time())

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": created,
        "model": model.get("id"),
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
        },
    }
