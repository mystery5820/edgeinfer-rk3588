from __future__ import annotations

from typing import Any, Dict, Optional, Set

RUNTIME_NAME = "phase19a-unified-inference-vlm-ready"

VLM_TASKS: Set[str] = {
    "vision-language",
    "image-captioning",
    "visual-question-answering",
    "multimodal-chat",
}


class VLMPlaceholderBackend:
    # Placeholder backend for planned VLM tasks.

    @staticmethod
    def backend_name() -> str:
        return "vlm-placeholder"

    @staticmethod
    def runtime_name() -> str:
        return RUNTIME_NAME

    @staticmethod
    def supported_tasks() -> Set[str]:
        return set(VLM_TASKS)

    @staticmethod
    def not_ready_detail(*, task: str, model: Optional[str] = None) -> Dict[str, Any]:
        return {
            "error": {
                "code": "vlm_backend_not_ready",
                "message": "VLM backend is planned but not implemented yet",
                "type": "edgeinfer_error",
                "retryable": False,
            },
            "edgeinfer": {
                "task": task,
                "model": model,
                "backend": VLMPlaceholderBackend.backend_name(),
                "runtime": VLMPlaceholderBackend.runtime_name(),
                "supported_vlm_tasks": sorted(VLM_TASKS),
                "note": "This task is reserved for future vision-language model integration.",
            },
        }
