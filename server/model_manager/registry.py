from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import default_registry_path, load_yaml


@dataclass
class ModelEntry:
    id: str
    name: str
    task: str
    backend: str
    quant: Optional[str] = None
    status: Optional[str] = None
    recommended: bool = False
    model_file: Optional[str] = None
    runtime: Optional[str] = None
    rknpu_driver: Optional[str] = None
    memory_manager: Optional[str] = None
    cma: Optional[str] = None
    ctx: Optional[int] = None
    max_new_tokens: Optional[int] = None
    init_ms: Optional[float] = None
    prefill_tps: Optional[float] = None
    generate_tps: Optional[float] = None
    peak_memory_mb: Optional[float] = None
    requirement: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ModelRegistry:
    def __init__(self, registry_path: str | Path | None = None):
        self.registry_path = Path(registry_path) if registry_path else default_registry_path()
        self.raw = load_yaml(self.registry_path)

    def list_models(self) -> List[Dict[str, Any]]:
        models: List[ModelEntry] = []

        models.extend(self._parse_qwen3_4b_status())
        models.extend(self._parse_generic_models())

        dedup: Dict[str, ModelEntry] = {}
        for model in models:
            dedup[model.id] = model

        return [m.to_dict() for m in dedup.values()]

    def get_model(self, model_id: str) -> Dict[str, Any]:
        for model in self.list_models():
            if model["id"] == model_id or model["name"] == model_id:
                return model
        raise KeyError(f"model not found: {model_id}")

    def get_default_model(self, task: str) -> Optional[Dict[str, Any]]:
        candidates = [m for m in self.list_models() if m.get("task") == task]
        recommended = [m for m in candidates if m.get("recommended")]
        if recommended:
            return recommended[0]
        if candidates:
            return candidates[0]
        return None

    def validate_model_entry(self, entry: Dict[str, Any]) -> List[str]:
        errors: List[str] = []

        required = ["id", "name", "task", "backend"]
        for key in required:
            if not entry.get(key):
                errors.append(f"missing required field: {key}")

        if entry.get("task") == "llm" and not entry.get("model_file"):
            errors.append("llm model missing model_file")

        return errors

    def _parse_qwen3_4b_status(self) -> List[ModelEntry]:
        block = self.raw.get("qwen3_4b_rkllm_status", {})
        if not isinstance(block, dict):
            return []

        result: List[ModelEntry] = []

        mapping = {
            "all_npu": "qwen3-4b-rkllm-all-npu",
            "hybrid": "qwen3-4b-rkllm-hybrid",
        }

        for variant, model_id in mapping.items():
            item = block.get(variant)
            if not isinstance(item, dict):
                continue

            result.append(
                ModelEntry(
                    id=model_id,
                    name=model_id,
                    task="llm",
                    backend="rkllm",
                    quant="w8a8",
                    status=item.get("status"),
                    recommended=bool(item.get("recommended", False)),
                    model_file=item.get("model_file"),
                    runtime=item.get("runtime"),
                    rknpu_driver=item.get("rknpu_driver"),
                    memory_manager=item.get("memory_manager"),
                    cma=item.get("cma"),
                    ctx=item.get("ctx"),
                    max_new_tokens=item.get("max_new_tokens"),
                    init_ms=item.get("init_ms"),
                    prefill_tps=item.get("prefill_tps"),
                    generate_tps=item.get("generate_tps"),
                    peak_memory_mb=item.get("peak_memory_mb"),
                    requirement=item.get("requirement"),
                    notes=f"Qwen3-4B RKLLM {variant}",
                )
            )

        return result

    def _parse_generic_models(self) -> List[ModelEntry]:
        """
        兼容未来 registry 中的通用 models 字段。
        支持两种形式：

        models:
          - id: xxx
            task: llm

        或：

        models:
          xxx:
            task: llm
        """
        raw_models = self.raw.get("models")
        if not raw_models:
            return []

        result: List[ModelEntry] = []

        if isinstance(raw_models, list):
            iterable = [(item.get("id") or item.get("name"), item) for item in raw_models if isinstance(item, dict)]
        elif isinstance(raw_models, dict):
            iterable = list(raw_models.items())
        else:
            return []

        for key, item in iterable:
            if not isinstance(item, dict) or not key:
                continue

            result.append(
                ModelEntry(
                    id=str(item.get("id", key)),
                    name=str(item.get("name", key)),
                    task=str(item.get("task", "unknown")),
                    backend=str(item.get("backend", item.get("runtime", "unknown"))),
                    quant=item.get("quant"),
                    status=item.get("status"),
                    recommended=bool(item.get("recommended", False)),
                    model_file=item.get("model_file"),
                    runtime=item.get("runtime"),
                    rknpu_driver=item.get("rknpu_driver"),
                    memory_manager=item.get("memory_manager"),
                    cma=item.get("cma"),
                    ctx=item.get("ctx"),
                    max_new_tokens=item.get("max_new_tokens"),
                    init_ms=item.get("init_ms"),
                    prefill_tps=item.get("prefill_tps"),
                    generate_tps=item.get("generate_tps"),
                    peak_memory_mb=item.get("peak_memory_mb"),
                    requirement=item.get("requirement"),
                    notes=item.get("notes"),
                )
            )

        return result
