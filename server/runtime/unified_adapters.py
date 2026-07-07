from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


RUNTIME_NAME = "phase19b-unified-response-adapter-polish"


@dataclass
class UnifiedAdapterResult:
    task: str
    model: Optional[str]
    adapter: str
    backend: str
    source_endpoint: Optional[str]
    source_runtime: Optional[str]
    summary: Dict[str, Any]
    data: Dict[str, Any]
    raw: Dict[str, Any]
    compatibility: Dict[str, Any] = field(default_factory=dict)


def _new_inference_id() -> str:
    return "infer-" + uuid.uuid4().hex[:12]


def to_plain_dict(value: Any) -> Dict[str, Any]:
    """Convert common API handler outputs into a plain dict.

    The task-specific handlers currently return dicts, but this helper keeps
    /v1/infer tolerant of Pydantic models or simple objects during future
    adapter work.
    """
    if isinstance(value, dict):
        return value

    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        if isinstance(dumped, dict):
            return dumped

    if hasattr(value, "dict"):
        dumped = value.dict()
        if isinstance(dumped, dict):
            return dumped

    return {"value": value}


def _compact_none(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _compact_none(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_compact_none(v) for v in obj]
    return obj


def build_unified_infer_response(result: UnifiedAdapterResult) -> Dict[str, Any]:
    """Build the Phase 19B unified /v1/infer response envelope.

    output.summary:
      Human- and frontend-friendly compact result.

    output.data:
      Normalized task result.

    output.raw:
      Full task-specific backend response for debugging and regression.

    For compatibility with Phase 19A tests and simple clients, selected
    task-specific fields are also copied into output when safe.
    """
    output: Dict[str, Any] = {
        "summary": _compact_none(result.summary),
        "data": _compact_none(result.data),
        "raw": result.raw,
    }

    for key, value in result.compatibility.items():
        output.setdefault(key, value)

    return {
        "id": _new_inference_id(),
        "object": "edgeinfer.inference",
        "created": int(time.time()),
        "task": result.task,
        "model": result.model,
        "output": output,
        "edgeinfer": {
            # Phase 19A compatibility fields for existing host clients.
            "task": result.task,
            "route": result.source_endpoint,
            "backend": result.backend,
            "runtime": RUNTIME_NAME,
            "source_endpoint": result.source_endpoint,
            "task_adapter": result.adapter,
            "source_runtime": result.source_runtime,
            "dispatch": {
                "task": result.task,
                "adapter": result.adapter,
                "source_endpoint": result.source_endpoint,
                "backend": result.backend,
                "source_runtime": result.source_runtime,
            },
            "note": (
                "Phase 19B normalizes /v1/infer output into "
                "summary/data/raw while preserving task-specific endpoints."
            ),
        },
    }


def _ordered_unique(values: list[Any]) -> list[Any]:
    seen = set()
    result = []
    for value in values:
        if value is None:
            continue
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _extract_latency(raw: Dict[str, Any]) -> Dict[str, Any]:
    latency = raw.get("latency_ms")
    if isinstance(latency, dict):
        return latency
    if isinstance(latency, (int, float)):
        return {"total": latency}

    timings = raw.get("timings") or raw.get("timing")
    if isinstance(timings, dict):
        return timings

    metrics = raw.get("metrics")
    if isinstance(metrics, dict):
        metrics_latency = metrics.get("latency_ms")
        if isinstance(metrics_latency, dict):
            return metrics_latency
        if isinstance(metrics_latency, (int, float)):
            return {"total": metrics_latency}

    return {}


def make_object_detection_adapter_result(
    *,
    task: str,
    requested_model: Optional[str],
    raw_output: Any,
) -> UnifiedAdapterResult:
    raw = to_plain_dict(raw_output)

    objects = raw.get("objects")
    if not isinstance(objects, list):
        objects = raw.get("detections")
    if not isinstance(objects, list):
        objects = []

    class_names = _ordered_unique(
        [
            obj.get("class_name")
            for obj in objects
            if isinstance(obj, dict)
        ]
    )

    first_obj = next((obj for obj in objects if isinstance(obj, dict)), {})
    image_info = raw.get("image")
    if not isinstance(image_info, dict):
        image_info = raw.get("image_metadata")
    if not isinstance(image_info, dict):
        image_info = raw.get("metadata")
    if not isinstance(image_info, dict):
        image_info = {}

    raw_edgeinfer = raw.get("edgeinfer") if isinstance(raw.get("edgeinfer"), dict) else {}

    summary = {
        "type": "object-detection",
        "num_objects": len(objects),
        "classes": class_names,
        "coordinate_space": first_obj.get("coordinate_space") or raw.get("coordinate_space") or "original_image",
        "box_format": first_obj.get("box_format") or raw.get("box_format") or "xyxy",
        "latency_ms": _extract_latency(raw),
        "image": {
            "path": image_info.get("path") or image_info.get("image_path"),
            "format": image_info.get("format"),
            "width": image_info.get("width") or image_info.get("image_width"),
            "height": image_info.get("height") or image_info.get("image_height"),
        },
    }

    data = {
        "objects": objects,
        "image": image_info,
    }

    # Backward-compatible fields for Phase 19A host tests and simple clients.
    # New clients should prefer output.summary / output.data / output.raw.
    compatibility = {
        "id": raw.get("id"),
        "object": raw.get("object"),
        "created": raw.get("created"),
        "model": raw.get("model") or requested_model,
        "image": image_info,
        "objects": objects,
        "latency_ms": raw.get("latency_ms"),
        "edgeinfer": raw.get("edgeinfer"),
    }

    return UnifiedAdapterResult(
        task=task,
        model=raw.get("model") or requested_model,
        adapter="vision-detect",
        backend=raw_edgeinfer.get("backend") or raw.get("backend") or "vision-adapter",
        source_endpoint="/v1/vision/detect",
        source_runtime=raw_edgeinfer.get("runtime"),
        summary=summary,
        data=data,
        raw=raw,
        compatibility=compatibility,
    )


def _extract_chat_text(raw: Dict[str, Any]) -> Optional[str]:
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        return None

    first = choices[0]
    if not isinstance(first, dict):
        return None

    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content

    text = first.get("text")
    if isinstance(text, str):
        return text

    return None


def make_chat_completion_adapter_result(
    *,
    task: str,
    requested_model: Optional[str],
    raw_output: Any,
) -> UnifiedAdapterResult:
    raw = to_plain_dict(raw_output)

    choices = raw.get("choices")
    if not isinstance(choices, list):
        choices = []

    usage = raw.get("usage")
    if not isinstance(usage, dict):
        usage = {}

    first_choice = choices[0] if choices and isinstance(choices[0], dict) else {}
    raw_edgeinfer = raw.get("edgeinfer") if isinstance(raw.get("edgeinfer"), dict) else {}

    summary = {
        "type": task,
        "num_choices": len(choices),
        "finish_reason": first_choice.get("finish_reason"),
        "text_preview": (_extract_chat_text(raw) or "")[:160],
        "usage": usage,
    }

    data = {
        "choices": choices,
        "usage": usage,
    }

    return UnifiedAdapterResult(
        task=task,
        model=raw.get("model") or requested_model,
        adapter="chat-completions",
        backend=raw_edgeinfer.get("backend") or "llm-adapter",
        source_endpoint="/v1/chat/completions",
        source_runtime=raw_edgeinfer.get("runtime"),
        summary=summary,
        data=data,
        raw=raw,
        compatibility={
            "id": raw.get("id"),
            "object": raw.get("object"),
            "created": raw.get("created"),
            "model": raw.get("model") or requested_model,
            "choices": choices,
            "usage": usage,
            "edgeinfer": raw.get("edgeinfer"),
        },
    )
