from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from typing import AsyncIterator, Dict, List, Literal, Optional, Union

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
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


class ResponseFormat(BaseModel):
    type: Literal["text", "json_object"]


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = Field(default="qwen3-4b-rkllm-all-npu")
    messages: List[ChatMessage]
    max_new_tokens: int = Field(default=128, ge=1, le=256)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=256)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    n: int = Field(default=1, ge=1)
    stream: bool = False
    stop: Optional[Union[str, List[str]]] = None
    response_format: Optional[ResponseFormat] = None


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


def _configured_rkllm_backend_name() -> str:
    if os.environ.get("EDGEINFER_FAKE_LLM", "0") == "1":
        return "fake"

    mode = os.environ.get("EDGEINFER_RKLLM_BACKEND_MODE", "oneshot").strip().lower()
    if mode in {"worker", "persistent", "persistent-worker"}:
        return "rkllm-persistent-worker"

    return "rkllm-runner"


def _request_field_was_set(req: BaseModel, field_name: str) -> bool:
    fields_set = getattr(req, "model_fields_set", None)
    if fields_set is None:
        fields_set = getattr(req, "__fields_set__", set())
    return field_name in fields_set


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
            "backend": _configured_rkllm_backend_name(),
            "llm": llm_queue.snapshot(),
        },
    }


def _effective_max_new_tokens(req: ChatCompletionRequest) -> int:
    max_tokens_was_set = _request_field_was_set(req, "max_tokens") and req.max_tokens is not None
    max_new_tokens_was_set = _request_field_was_set(req, "max_new_tokens")

    if max_tokens_was_set and max_new_tokens_was_set and req.max_tokens != req.max_new_tokens:
        raise HTTPException(
            status_code=400,
            detail=_error_detail(
                code="token_limit_conflict",
                message="max_tokens and max_new_tokens cannot both be set to different values",
                model_id=req.model,
                retryable=False,
            ),
        )

    if max_tokens_was_set:
        return int(req.max_tokens)

    return int(req.max_new_tokens)


def _normalize_stop_sequences(req: ChatCompletionRequest) -> List[str]:
    if req.stop is None:
        return []

    if isinstance(req.stop, str):
        stop_sequences = [req.stop]
    else:
        stop_sequences = list(req.stop)

    for stop_sequence in stop_sequences:
        if not isinstance(stop_sequence, str) or stop_sequence == "":
            raise HTTPException(
                status_code=400,
                detail=_error_detail(
                    code="invalid_stop",
                    message="stop must be a non-empty string or a list of non-empty strings",
                    model_id=req.model,
                    retryable=False,
                ),
            )

    return stop_sequences


def _apply_stop_sequences(text: str, stop_sequences: List[str]) -> tuple[str, Optional[str]]:
    if not stop_sequences:
        return text, None

    earliest_index: Optional[int] = None
    matched_stop: Optional[str] = None

    for stop_sequence in stop_sequences:
        index = text.find(stop_sequence)
        if index >= 0 and (earliest_index is None or index < earliest_index):
            earliest_index = index
            matched_stop = stop_sequence

    if earliest_index is None:
        return text, None

    return text[:earliest_index], matched_stop


def _validate_response_format(req: ChatCompletionRequest) -> None:
    if req.response_format is None:
        return

    if req.response_format.type == "text":
        return

    raise HTTPException(
        status_code=400,
        detail=_error_detail(
            code="response_format_not_supported",
            message="response_format values other than {'type': 'text'} are not supported in Phase 9 MVP",
            model_id=req.model,
            retryable=False,
        ),
    )


def _validate_top_p(req: ChatCompletionRequest) -> None:
    if abs(float(req.top_p) - 1.0) < 1e-9:
        return

    raise HTTPException(
        status_code=400,
        detail=_error_detail(
            code="top_p_not_supported",
            message="top_p values other than 1.0 are not supported in Phase 9 MVP",
            model_id=req.model,
            retryable=False,
        ),
    )


def _validate_n(req: ChatCompletionRequest) -> None:
    if req.n == 1:
        return

    raise HTTPException(
        status_code=400,
        detail=_error_detail(
            code="n_not_supported",
            message="n values other than 1 are not supported in Phase 9 MVP",
            model_id=req.model,
            retryable=False,
        ),
    )

def _json_sse(payload: Dict[str, object]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _done_sse() -> str:
    return "data: [DONE]\n\n"


def _stream_chunk(
    *,
    chunk_id: str,
    created: int,
    model_id: str,
    delta: Dict[str, object],
    finish_reason: Optional[str] = None,
    edgeinfer: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    payload: Dict[str, object] = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model_id,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }

    if edgeinfer is not None:
        payload["edgeinfer"] = edgeinfer

    return payload


def _filter_stream_delta(
    *,
    delta: str,
    stop_sequences: List[str],
    pending: str,
) -> tuple[Optional[str], str, Optional[str]]:
    if not stop_sequences:
        return delta, "", None

    combined = pending + delta

    earliest_index: Optional[int] = None
    matched_stop: Optional[str] = None

    for stop_sequence in stop_sequences:
        idx = combined.find(stop_sequence)
        if idx >= 0 and (earliest_index is None or idx < earliest_index):
            earliest_index = idx
            matched_stop = stop_sequence

    if earliest_index is not None:
        return combined[:earliest_index], "", matched_stop

    keep = max(0, max(len(s) for s in stop_sequences) - 1)
    if keep <= 0:
        return combined, "", None

    safe_len = max(0, len(combined) - keep)
    return combined[:safe_len], combined[safe_len:], None


async def _stream_chat_events(
    *,
    req: ChatCompletionRequest,
    backend: RKLLMBackend,
    prompt: str,
    model: Dict[str, object],
    model_id: str,
    effective_max_new_tokens: int,
    stop_sequences: List[str],
    lease,
) -> AsyncIterator[str]:
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    matched_stop: Optional[str] = None
    pending_stop = ""
    stream_stopped = False
    success = False

    try:
        yield _json_sse(
            _stream_chunk(
                chunk_id=chunk_id,
                created=created,
                model_id=model_id,
                delta={"role": "assistant"},
                finish_reason=None,
                edgeinfer={
                    "backend": _configured_rkllm_backend_name(),
                    "stream": True,
                },
            )
        )

        async for raw_delta in backend.generate_stream(
            prompt=prompt,
            model=model,
            max_new_tokens=effective_max_new_tokens,
            timeout_seconds=LLM_TIMEOUT_SECONDS,
        ):
            if stream_stopped:
                continue

            delta, pending_stop, matched = _filter_stream_delta(
                delta=raw_delta,
                stop_sequences=stop_sequences,
                pending=pending_stop,
            )

            if matched is not None:
                matched_stop = matched
                stream_stopped = True

            if delta:
                yield _json_sse(
                    _stream_chunk(
                        chunk_id=chunk_id,
                        created=created,
                        model_id=model_id,
                        delta={"content": delta},
                        finish_reason=None,
                    )
                )

        if not stream_stopped and pending_stop:
            yield _json_sse(
                _stream_chunk(
                    chunk_id=chunk_id,
                    created=created,
                    model_id=model_id,
                    delta={"content": pending_stop},
                    finish_reason=None,
                )
            )

        yield _json_sse(
            _stream_chunk(
                chunk_id=chunk_id,
                created=created,
                model_id=model_id,
                delta={},
                finish_reason="stop",
                edgeinfer={
                    "backend": _configured_rkllm_backend_name(),
                    "stream": True,
                    "stop": {
                        "requested": stop_sequences,
                        "matched": matched_stop,
                    },
                },
            )
        )
        yield _done_sse()

        success = True
        lease.finish_success()

    except asyncio.CancelledError as exc:
        lease.finish_error(exc)
        raise

    except Exception as exc:
        lease.finish_error(exc)
        error_payload: Dict[str, object] = {
            "error": {
                "code": "rkllm_stream_runtime_error",
                "message": str(exc),
                "type": "edgeinfer_error",
                "retryable": False,
            },
            "edgeinfer": {
                "model": model_id,
                "backend": _configured_rkllm_backend_name(),
                "stream": True,
                "llm": llm_queue.snapshot(),
            },
        }
        yield _json_sse(error_payload)
        yield _done_sse()

    finally:
        if not success and not lease.released:
            lease.finish_error("stream closed before completion")


async def _stream_chat_completion(
    *,
    req: ChatCompletionRequest,
    backend: RKLLMBackend,
    prompt: str,
    model: Dict[str, object],
    model_id: str,
    effective_max_new_tokens: int,
    stop_sequences: List[str],
):
    if not backend.supports_stream():
        raise HTTPException(
            status_code=400,
            detail=_error_detail(
                code="stream_backend_not_supported",
                message="stream=true currently requires rkllm-persistent-worker backend",
                model_id=model_id,
                retryable=False,
            ),
        )

    try:
        lease = await llm_queue.acquire_nowait(model_id=model_id)
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

    return StreamingResponse(
        _stream_chat_events(
            req=req,
            backend=backend,
            prompt=prompt,
            model=model,
            model_id=model_id,
            effective_max_new_tokens=effective_max_new_tokens,
            stop_sequences=stop_sequences,
            lease=lease,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )




@router.post("/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    _validate_n(req)
    _validate_top_p(req)
    _validate_response_format(req)

    effective_max_new_tokens = _effective_max_new_tokens(req)
    stop_sequences = _normalize_stop_sequences(req)

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

    if req.stream:
        return await _stream_chat_completion(
            req=req,
            backend=backend,
            prompt=prompt,
            model=model,
            model_id=model_id,
            effective_max_new_tokens=effective_max_new_tokens,
            stop_sequences=stop_sequences,
        )

    try:
        result = await llm_queue.run_nowait(
            lambda: backend.generate(
                prompt=prompt,
                model=model,
                max_new_tokens=effective_max_new_tokens,
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

    response_text, matched_stop = _apply_stop_sequences(result["text"], stop_sequences)
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
                    "content": response_text,
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
            "stop": {
                "requested": stop_sequences,
                "matched": matched_stop,
            },
        },
    }
