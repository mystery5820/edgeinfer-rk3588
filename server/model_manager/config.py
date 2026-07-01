from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml


PROJECT_ROOT = Path(os.environ.get("EDGEINFER_ROOT", Path(__file__).resolve().parents[2]))


def load_yaml(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p

    if not p.exists():
        raise FileNotFoundError(f"YAML file not found: {p}")

    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return data or {}


def default_registry_path() -> Path:
    return PROJECT_ROOT / "configs" / "model_registry.yaml"
